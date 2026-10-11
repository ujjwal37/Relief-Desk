import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.config import settings
from app.models.firestore_models import (
    StoredReport,
    StoredRequest,
    StoredCluster,
    AuditEntry,
    RequestStatus,
    StoredResource,
    ResourceKind,
    ResourceStatus,
    StoredMatch,
    MatchState,
    MatchBreakdown,
)

logger = logging.getLogger("relief_desk.storage")


class StorageService:
    def __init__(self):
        self._reports: Dict[str, StoredReport] = {}
        self._requests: Dict[str, StoredRequest] = {}
        self._clusters: Dict[str, StoredCluster] = {}
        self._resources: Dict[str, StoredResource] = {}
        self._matches: Dict[str, StoredMatch] = {}
        self._audit_log: List[AuditEntry] = []  # Strictly append-only
        self._idempotent: Dict[str, Dict[str, Any]] = {}
        self._submit_lock = threading.Lock()
        self._firestore_client = None
        self._init_firestore()

    def _init_firestore(self):
        try:
            import socket
            if settings.FIRESTORE_EMULATOR_HOST:
                host, port_str = settings.FIRESTORE_EMULATOR_HOST.split(":")
                with socket.create_connection((host, int(port_str)), timeout=0.2):
                    pass
                from google.cloud import firestore  # type: ignore
                self._firestore_client = firestore.Client(project=settings.GCP_PROJECT_ID)
                logger.info("Connected to Firestore emulator at %s", settings.FIRESTORE_EMULATOR_HOST)
        except Exception:
            # Firestore emulator not currently running, operate gracefully in in-memory mode
            self._firestore_client = None

    # --- Append-Only Audit Trail ---
    def record_audit(
        self,
        actor: str,
        action: str,
        target: str,
        before: Optional[Dict[str, Any]] = None,
        after: Optional[Dict[str, Any]] = None,
    ) -> AuditEntry:
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        entry = AuditEntry(
            id=audit_id,
            actor=actor,
            action=action,
            target=target,
            before=before,
            after=after,
            ts=datetime.now(timezone.utc).isoformat(),
        )
        self._audit_log.append(entry)
        logger.info("AUDIT [%s] %s on %s by %s", entry.ts, action, target, actor)
        return entry

    def get_audit_trail(self, target: Optional[str] = None) -> List[AuditEntry]:
        if target:
            return [e for e in self._audit_log if e.target == target]
        return list(self._audit_log)

    # --- Reports DAO ---
    def save_report_raw(
        self,
        raw_text: str,
        channel: str = "text",
        lang: str = "en",
        source_id: str = "anon",
        trust_level: str = "anonymous",
        event_id: str = "event_riverbend_flood",
        pack_id: str = "flood",
        flags: Optional[List[str]] = None,
        status_token: Optional[str] = None,
        transcript: Optional[str] = None,
        asr_confidence: Optional[float] = None,
        report_id: Optional[str] = None,
    ) -> StoredReport:
        """Stores incoming report raw immediately so nothing is ever lost."""
        report_id = report_id or f"rep_{uuid.uuid4().hex[:10]}"
        report = StoredReport(
            id=report_id,
            event_id=event_id,
            pack_id=pack_id,
            channel=channel,
            lang=lang,
            raw_text=raw_text,
            transcript=transcript,
            asr_confidence=asr_confidence,
            source_id=source_id,
            trust_level=trust_level,
            flags=flags or [],
            status_token=status_token,
        )
        self._reports[report_id] = report
        self.record_audit(
            actor="public_intake",
            action="report_stored_raw",
            target=report_id,
            after=report.model_dump()
        )
        return report

    def get_report(self, report_id: str) -> Optional[StoredReport]:
        return self._reports.get(report_id)

    def get_report_by_status_token(self, token: str) -> Optional[StoredReport]:
        for rep in self._reports.values():
            if rep.status_token == token:
                return rep
        return None

    def list_reports(self) -> List[StoredReport]:
        return list(self._reports.values())

    def get_idempotent(self, key: Optional[str]) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        with self._submit_lock:
            body = self._idempotent.get(key)
            return dict(body) if body else None

    def begin_or_replay(self, key: Optional[str]) -> Optional[Dict[str, Any]]:
        """Reserve a new key, or return the stored body / an in-flight marker."""
        if not key:
            return None
        with self._submit_lock:
            existing = self._idempotent.get(key)
            if existing and existing.get("request_id"):
                return dict(existing)
            if existing and existing.get("_inflight"):
                return {"_inflight": True}
            self._idempotent[key] = {"_inflight": True}
            return None

    def save_idempotent(self, key: Optional[str], body: Dict[str, Any]) -> None:
        if not key:
            return
        with self._submit_lock:
            self._idempotent[key] = dict(body)

    def release_idempotent(self, key: Optional[str]) -> None:
        """Drop a reservation when submit fails, so the phone can retry the same key."""
        if not key:
            return
        with self._submit_lock:
            existing = self._idempotent.get(key)
            if existing and existing.get("_inflight") and not existing.get("request_id"):
                self._idempotent.pop(key, None)

    # --- Requests DAO ---
    def save_request(self, req: StoredRequest, actor: str = "system") -> StoredRequest:
        before = self._requests.get(req.id).model_dump() if req.id in self._requests else None
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        self.record_audit(
            actor=actor,
            action="request_saved" if before else "request_created",
            target=req.id,
            before=before,
            after=req.model_dump(),
        )
        return req

    def get_request(self, request_id: str) -> Optional[StoredRequest]:
        return self._requests.get(request_id)

    def list_requests(self, status: Optional[RequestStatus] = None) -> List[StoredRequest]:
        reqs = list(self._requests.values())
        if status:
            return [r for r in reqs if r.status == status]
        return reqs

    def update_request_status(
        self, request_id: str, new_status: RequestStatus, actor: str = "coordinator"
    ) -> Optional[StoredRequest]:
        req = self._requests.get(request_id)
        if not req:
            return None
        before = req.model_dump()
        req.status = new_status
        req.version += 1
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[request_id] = req
        self.record_audit(
            actor=actor,
            action="status_change",
            target=request_id,
            before=before,
            after=req.model_dump(),
        )
        return req

    # --- Clusters DAO ---
    def create_cluster(
        self, request_ids: List[str], evidence: List[str], merged_by: str = "auto_suggest"
    ) -> StoredCluster:
        cluster_id = f"clust_{uuid.uuid4().hex[:10]}"
        cluster = StoredCluster(
            id=cluster_id,
            request_ids=request_ids,
            evidence=evidence,
            merged_by=merged_by,
            undone=False,
        )
        self._clusters[cluster_id] = cluster

        # Assign cluster_id to each member request
        for r_id in request_ids:
            if r_id in self._requests:
                r = self._requests[r_id]
                r.cluster_id = cluster_id
                r.updated_at = datetime.now(timezone.utc).isoformat()

        self.record_audit(
            actor=merged_by,
            action="cluster_created",
            target=cluster_id,
            after=cluster.model_dump(),
        )
        return cluster

    def split_cluster(self, cluster_id: str, actor: str = "coordinator") -> Optional[StoredCluster]:
        cluster = self._clusters.get(cluster_id)
        if not cluster:
            return None
        before = cluster.model_dump()
        cluster.undone = True
        cluster.updated_at = datetime.now(timezone.utc).isoformat()

        # Detach cluster_id from requests
        for r_id in cluster.request_ids:
            if r_id in self._requests:
                r = self._requests[r_id]
                r.cluster_id = None
                r.updated_at = datetime.now(timezone.utc).isoformat()

        self.record_audit(
            actor=actor,
            action="cluster_split",
            target=cluster_id,
            before=before,
            after=cluster.model_dump(),
        )
        return cluster

    def get_cluster(self, cluster_id: str) -> Optional[StoredCluster]:
        return self._clusters.get(cluster_id)

    def list_clusters(self) -> List[StoredCluster]:
        return list(self._clusters.values())

    # --- Resources DAO & Capacity Transactions ---
    def save_resource(self, res: StoredResource, actor: str = "system") -> StoredResource:
        before = self._resources.get(res.id).model_dump() if res.id in self._resources else None
        res.updated_at = datetime.now(timezone.utc).isoformat()
        self._resources[res.id] = res
        self.record_audit(
            actor=actor,
            action="resource_saved" if before else "resource_created",
            target=res.id,
            before=before,
            after=res.model_dump(),
        )
        return res

    def get_resource(self, resource_id: str) -> Optional[StoredResource]:
        return self._resources.get(resource_id)

    def list_resources(
        self, kind: Optional[ResourceKind] = None, event_id: str = "event_riverbend_flood"
    ) -> List[StoredResource]:
        res_list = [r for r in self._resources.values() if r.event_id == event_id]
        if kind:
            return [r for r in res_list if r.kind == kind]
        return res_list

    def reserve_capacity(
        self,
        resource_id: str,
        amount: int,
        allow_overcommit: bool = False,
        actor: str = "coordinator",
    ) -> tuple[StoredResource, bool]:
        """Decrements capacity on approval. Returns (resource, is_overcommitted).
        Raises ValueError if amount > capacity_remaining and allow_overcommit is False."""
        res = self._resources.get(resource_id)
        if not res:
            raise ValueError(f"Resource {resource_id} not found")

        before = res.model_dump()
        is_overcommit = amount > res.capacity_remaining

        if is_overcommit and not allow_overcommit:
            raise ValueError(
                f"Overcommit warning: Requested {amount} exceeds available capacity {res.capacity_remaining} for {res.name}"
            )

        new_remaining = res.capacity_remaining - amount
        res.capacity_remaining = max(0, new_remaining)
        if res.capacity_remaining == 0:
            res.status = ResourceStatus.DEPLETED
        else:
            res.status = ResourceStatus.BUSY

        res.updated_at = datetime.now(timezone.utc).isoformat()
        self._resources[resource_id] = res

        self.record_audit(
            actor=actor,
            action="capacity_reserved",
            target=resource_id,
            before=before,
            after={
                **res.model_dump(),
                "reserved_amount": amount,
                "overcommit": is_overcommit,
                "overcommit_override": allow_overcommit,
            },
        )
        return res, is_overcommit

    def release_capacity(
        self, resource_id: str, amount: int, actor: str = "coordinator"
    ) -> StoredResource:
        """Releases/restores capacity on match cancellation or dispatch completion."""
        res = self._resources.get(resource_id)
        if not res:
            raise ValueError(f"Resource {resource_id} not found")

        before = res.model_dump()
        res.capacity_remaining = min(res.capacity_total, res.capacity_remaining + amount)
        if res.capacity_remaining > 0:
            res.status = ResourceStatus.AVAILABLE
        res.updated_at = datetime.now(timezone.utc).isoformat()
        self._resources[resource_id] = res

        self.record_audit(
            actor=actor,
            action="capacity_released",
            target=resource_id,
            before=before,
            after={**res.model_dump(), "released_amount": amount},
        )
        return res

    def load_seed_resources(self, yaml_path: Optional[str] = None) -> int:
        """Loads seed resources from YAML file into storage."""
        import os
        import yaml
        if yaml_path is None:
            # storage.py is at services/api/app/tools/storage.py (4 levels deep from project root)
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
            yaml_path = os.path.join(base_dir, "data", "synthetic", "flood_v1", "resources.yaml")

        if not os.path.exists(yaml_path):
            logger.warning("Resources YAML not found at %s", yaml_path)
            return 0

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        count = 0
        for item in data.get("resources", []):
            res = StoredResource(
                id=item["id"],
                event_id=item.get("event_id", data.get("event_id", "event_riverbend_flood")),
                pack_id=item.get("pack_id", data.get("scenario_pack", "flood")),
                kind=ResourceKind(item["kind"]),
                name=item["name"],
                name_hi=item.get("name_hi"),
                ward_id=item["ward_id"],
                lat=float(item["lat"]),
                lng=float(item["lng"]),
                capacity_total=int(item["capacity_total"]),
                capacity_remaining=int(item.get("capacity_remaining", item["capacity_total"])),
                status=ResourceStatus(item.get("status", "available")),
                synthetic=bool(item.get("synthetic", True)),
            )
            self._resources[res.id] = res
            count += 1
        logger.info("Loaded %d synthetic seed resources from %s", count, yaml_path)
        return count

    # --- Matches DAO ---
    def save_match(self, match: StoredMatch, actor: str = "system") -> StoredMatch:
        before = self._matches.get(match.id).model_dump() if match.id in self._matches else None
        match.updated_at = datetime.now(timezone.utc).isoformat()
        self._matches[match.id] = match
        self.record_audit(
            actor=actor,
            action="match_saved" if before else "match_created",
            target=match.id,
            before=before,
            after=match.model_dump(),
        )
        return match

    def get_match(self, match_id: str) -> Optional[StoredMatch]:
        return self._matches.get(match_id)

    def list_matches_for_request(self, request_id: str) -> List[StoredMatch]:
        return [m for m in self._matches.values() if m.request_id == request_id]

    def approve_match(
        self,
        match_id: str,
        approved_by: str = "coordinator",
        allow_overcommit: bool = False,
    ) -> StoredMatch:
        """Approves dispatch: decrements resource capacity, updates match and request state."""
        match = self._matches.get(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        req = self._requests.get(match.request_id)
        people_needed = req.people_count if (req and req.people_count) else 1

        # Decrement capacity
        _, is_overcommit = self.reserve_capacity(
            resource_id=match.resource_id,
            amount=people_needed,
            allow_overcommit=allow_overcommit,
            actor=approved_by,
        )

        before = match.model_dump()
        match.state = MatchState.APPROVED
        match.approved_by = approved_by
        match.overcommit = is_overcommit
        match.overcommit_override = allow_overcommit
        match.updated_at = datetime.now(timezone.utc).isoformat()
        self._matches[match_id] = match

        if req:
            req.status = RequestStatus.APPROVED
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._requests[req.id] = req

        self.record_audit(
            actor=approved_by,
            action="match_approved",
            target=match_id,
            before=before,
            after=match.model_dump(),
        )
        return match

    def reject_match(
        self, match_id: str, reason: str, actor: str = "coordinator"
    ) -> StoredMatch:
        match = self._matches.get(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        before = match.model_dump()
        match.state = MatchState.REJECTED
        match.rejected_reason = reason
        match.updated_at = datetime.now(timezone.utc).isoformat()
        self._matches[match_id] = match

        self.record_audit(
            actor=actor,
            action="match_rejected",
            target=match_id,
            before=before,
            after=match.model_dump(),
        )
        return match

    def load_seed_incidents(self, yaml_path: Optional[str] = None, pack_id: str = "flood") -> int:
        """Loads seeded flood incidents into storage requests."""
        import os
        import yaml
        from app.models.schemas import FieldConfidences, IncidentType, HazardType, VulnerableFlags
        from app.tools.scoring import scoring_engine

        if yaml_path is None:
            base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
            yaml_path = os.path.join(base_dir, "data", "synthetic", "flood_v1", "seeds.yaml")

        if not os.path.exists(yaml_path):
            return 0

        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        count = 0
        for item in data.get("incidents", []):
            try:
                vuln_data = item.get("vulnerable", {})
                vuln = VulnerableFlags(
                    child=bool(vuln_data.get("child")),
                    elderly=bool(vuln_data.get("elderly")),
                    disabled=bool(vuln_data.get("disabled")),
                    pregnant=bool(vuln_data.get("pregnant")),
                    medical_need=bool(vuln_data.get("medical_need")),
                )

                sample_reports = item.get("sample_reports", [])
                raw_text = None
                ai_translation = None
                translations_map: Dict[str, str] = {}
                for sr in sample_reports:
                    s_lang = sr.get("lang")
                    s_txt = sr.get("text")
                    if s_lang and s_txt:
                        translations_map[s_lang] = s_txt
                    if s_lang in ("hi", "hinglish", "ta"):
                        raw_text = s_txt
                    elif s_lang == "en":
                        ai_translation = s_txt
                if not raw_text and sample_reports:
                    raw_text = sample_reports[0].get("text")
                if not ai_translation:
                    ai_translation = item.get("description", "")
                if "en" not in translations_map and ai_translation:
                    translations_map["en"] = ai_translation
                if "hi" not in translations_map and raw_text:
                    translations_map["hi"] = raw_text

                flags_list = list(item.get("flags", []))

                req = StoredRequest(
                    id=item["id"],
                    pack_id=item.get("pack_id") or pack_id,
                    type=IncidentType(item.get("type", "rescue")),
                    place_text=item.get("description", ""),
                    ward_id=item.get("ward_id"),
                    lat=float(item.get("lat", 26.85)),
                    lng=float(item.get("lng", 80.94)),
                    people_count=int(item.get("people", 1)),
                    vulnerable=vuln,
                    hazard=HazardType(item.get("hazard", "unknown")),
                    status=RequestStatus.NEW,
                    flags=flags_list,
                    raw_text=raw_text,
                    ai_translation=ai_translation,
                    translations=translations_map,
                    translation_confidence=0.92,
                    confidence=FieldConfidences(
                        type=0.96,
                        place=0.88,
                        people=0.82,
                        vulnerable=0.91,
                        urgency=0.94,
                    ),
                )
                urg_res = scoring_engine.compute_urgency(req)
                req.urgency_score = urg_res.score
                req.urgency_reason = urg_res.reason

                # Hero demo case: INC-001 has merged duplicates and update
                if req.id == "INC-001":
                    req.merged_count = 3
                    req.update_count = 1
                    cluster_id = f"cl_seed_{req.id}"
                    req.cluster_id = cluster_id
                    cluster = StoredCluster(
                        id=cluster_id,
                        request_ids=[req.id, "INC-001-dup1", "INC-001-dup2"],
                        evidence=[
                            "3 reports, same lane, within 9 min",
                            "Now 5 people = update, urgency raised",
                        ],
                        merged_by="dedupe_agent",
                    )
                    self._clusters[cluster.id] = cluster

                self._requests[req.id] = req
                count += 1
            except Exception as e:
                logger.warning("Error loading seed incident %s: %s", item.get("id"), e)
        logger.info("Loaded %d synthetic seed incidents into storage.", count)
        return count

    def load_scenario_pack_seeds(self) -> int:
        """Load data/synthetic/<scenario-id>/seeds.yaml for every pack. No per-scenario branch."""
        import os
        from app.tools.scenario_loader import scenario_registry

        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../.."))
        loaded = 0
        for scenario in scenario_registry.list_scenarios():
            path = os.path.join(base_dir, "data", "synthetic", scenario.id, "seeds.yaml")
            if os.path.exists(path):
                loaded += self.load_seed_incidents(path, pack_id=scenario.id)
        return loaded


# Singleton instance
storage_service = StorageService()
# Auto-load seed resources and incidents
try:
    storage_service.load_seed_resources()
    storage_service.load_seed_incidents()
    storage_service.load_scenario_pack_seeds()
    if settings.DEMO_MODE:
        from app.tools.demo_seed import load_demo_pack
        load_demo_pack(storage_service)
except Exception:
    pass


