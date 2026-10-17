import logging
import os
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional
from app.config import settings
from app.models.firestore_models import (
    StoredReport,
    StoredRequest,
    StoredCluster,
    AuditEntry,
    RequestStatus,
    StoredResource,
    LocationPoint,
    ResourceKind,
    ResourceStatus,
    StoredMatch,
    MatchState,
    MatchBreakdown,
)

logger = logging.getLogger("relief_desk.storage")

# The default demo is two Kuttanad cases and the teams that sit within 15 km of them.
# DEMO_SEED=full loads every incident in the flood pack. Reset always returns here.
SMALL_CASE_IDS = ("INC-001", "INC-002")
SMALL_TEAM_IDS = ("RES-BOAT-01", "RES-MED-02", "RES-FOOD-03", "RES-SHELTER-02")


def active_seed_mode() -> str:
    """small unless DEMO_SEED=full. Pytest keeps the full pack unless the env var says small."""
    explicit = os.environ.get("DEMO_SEED", "").strip().lower()
    if explicit in ("full", "small"):
        return explicit
    if "pytest" in sys.modules:
        return "full"
    mode = (getattr(settings, "DEMO_SEED", None) or "small").strip().lower()
    return mode if mode in ("full", "small") else "small"


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
        # Re-entrant: approve releases sibling holds while it already holds this lock.
        self._hold_lock = threading.RLock()
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
        try:
            from app.tools.events import emit_audit
            emit_audit(action, target, after)
        except Exception:
            logger.debug("Event bus did not publish %s", action, exc_info=True)
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
        event_id: str = "event_kerala_flood",
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

        # Detach the cluster and release a folded report so undo puts it back on the board.
        member_ids = set(cluster.request_ids)
        for r_id in cluster.request_ids:
            if r_id not in self._requests:
                continue
            req = self._requests[r_id]
            req.cluster_id = None
            if req.merged_into in member_ids:
                parent = self._requests.get(req.merged_into)
                if parent and (parent.merged_count or 1) > 1:
                    parent.merged_count = (parent.merged_count or 1) - 1
                req.merged_into = None
                req.merged_count = 1
            req.updated_at = datetime.now(timezone.utc).isoformat()

        # Seed clusters can list report ids that were never stored. Those ghosts
        # never had merged_into, so the loop above left the parent's count high
        # and the chip stayed after undo. Recount from requests that still exist.
        for r_id in cluster.request_ids:
            req = self._requests.get(r_id)
            if req is None or req.merged_into:
                continue
            still = sum(1 for other in self._requests.values() if other.merged_into == req.id)
            req.merged_count = 1 + still

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
        self, kind: Optional[ResourceKind] = None, event_id: str = "event_kerala_flood"
    ) -> List[StoredResource]:
        res_list = [r for r in self._resources.values() if r.event_id == event_id]
        if settings.DEMO_MODE:
            simulate_demo_checkins(res_list)
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
            res.status = ResourceStatus.DISPATCHED

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

    def reserve_hold(self, request_id: str, resource_id: str, amount: int, actor: str = "dispatcher") -> dict:
        """Claim seats without dispatching. A second claim on the same team fails."""
        with self._hold_lock:
            res = self._resources.get(resource_id)
            if not res:
                raise ValueError(f"Resource {resource_id} not found")
            if res.hold_request_id == request_id:
                return {"held": True, "resource_id": resource_id, "amount": res.hold_amount, "dispatched": False}
            if res.hold_request_id or amount > res.capacity_remaining:
                free = 0 if res.hold_request_id else res.capacity_remaining
                raise ValueError(f"shortage: {amount} seats requested and {free} are free on {res.name}")
            before = res.model_dump()
            res.capacity_remaining -= amount
            res.hold_request_id = request_id
            res.hold_amount = amount
            res.updated_at = datetime.now(timezone.utc).isoformat()
            self._resources[resource_id] = res
            self.record_audit(
                actor=actor,
                action="capacity_reserved",
                target=resource_id,
                before=before,
                after={**res.model_dump(), "hold": True, "reserved_amount": amount},
            )
            return {"held": True, "resource_id": resource_id, "amount": amount, "dispatched": False}

    def release_hold(self, resource_id: str, actor: str = "coordinator") -> Optional[StoredResource]:
        """Give a rejected proposal's seats back. Does nothing when there is no hold."""
        with self._hold_lock:
            res = self._resources.get(resource_id)
            if not res or not res.hold_request_id:
                return res
            before = res.model_dump()
            amount = res.hold_amount or 0
            res.capacity_remaining = min(res.capacity_total, res.capacity_remaining + amount)
            res.hold_request_id = None
            res.hold_amount = 0
            if res.capacity_remaining > 0 and res.status == ResourceStatus.DEPLETED:
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

    def update_resource_location(
        self, resource_id: str, lat: float, lng: float, actor: str = "coordinator"
    ) -> StoredResource:
        """Coordinator sets a team's last-known point. Stops a running simulation."""
        res = self._resources.get(resource_id)
        if not res:
            raise ValueError(f"Resource {resource_id} not found")
        before = res.model_dump()
        res.lat = lat
        res.lng = lng
        res.location_updated_at = datetime.now(timezone.utc).isoformat()
        res.updated_at = res.location_updated_at
        res.simulated = False
        res.sim_step = 0
        self._append_trail(res)
        self._resources[resource_id] = res
        self.record_audit(
            actor=actor, action="location_update", target=resource_id, before=before, after=res.model_dump()
        )
        return res

    def begin_simulation(self, resource_id: str, target_lat: float, target_lng: float, launch: bool = True) -> None:
        """Move a team in a straight line toward the case. Labelled simulated. Not a live GPS feed."""
        res = self._resources.get(resource_id)
        if not res:
            return
        res.sim_origin_lat = res.lat
        res.sim_origin_lng = res.lng
        res.sim_target_lat = target_lat
        res.sim_target_lng = target_lng
        res.sim_step = 0
        res.simulated = True
        res.status = ResourceStatus.EN_ROUTE
        res.location_updated_at = datetime.now(timezone.utc).isoformat()
        self._append_trail(res)
        self._resources[resource_id] = res

        def run() -> None:
            for _ in range(4):
                time.sleep(3)
                current = self._resources.get(resource_id)
                if not current or not current.simulated or current.sim_step >= 4:
                    return
                self.step_simulation(resource_id)

        if launch:
            threading.Thread(target=run, name=f"sim-{resource_id}", daemon=True).start()

    def step_simulation(self, resource_id: str) -> Optional[StoredResource]:
        res = self._resources.get(resource_id)
        if not res or not res.simulated or res.sim_origin_lat is None or res.sim_target_lat is None:
            return res
        if res.sim_origin_lng is None or res.sim_target_lng is None:
            return res
        res.sim_step += 1
        frac = min(1.0, res.sim_step / 4)
        res.lat = res.sim_origin_lat + (res.sim_target_lat - res.sim_origin_lat) * frac
        res.lng = res.sim_origin_lng + (res.sim_target_lng - res.sim_origin_lng) * frac
        res.location_updated_at = datetime.now(timezone.utc).isoformat()
        res.status = ResourceStatus.ON_SCENE if frac >= 1 else ResourceStatus.EN_ROUTE
        self._append_trail(res)
        self._resources[resource_id] = res
        if frac >= 1 and res.assigned_request_id:
            # The simulated team reached the pin: the case is in progress, same as a field "at scene".
            target = self._requests.get(res.assigned_request_id)
            if target is not None and target.status in (RequestStatus.DISPATCHED, RequestStatus.APPROVED):
                try:
                    self.mark_arrived(target.id, actor="simulation")
                except ValueError:
                    pass
        return res

    def _append_trail(self, res: StoredResource) -> None:
        res.location_trail.append(LocationPoint(
            lat=res.lat,
            lng=res.lng,
            at=res.location_updated_at or datetime.now(timezone.utc).isoformat(),
        ))
        if len(res.location_trail) > 40:
            res.location_trail = res.location_trail[-40:]

    def team_action(self, resource_id: str, action: str, actor: str = "team") -> StoredResource:
        """Field confirmation: at the scene, job done, or back in the pool."""
        res = self._resources.get(resource_id)
        if not res:
            raise ValueError(f"Resource {resource_id} not found")
        if action == "at_scene":
            res.status = ResourceStatus.ON_SCENE
            res.simulated = False
            res.updated_at = datetime.now(timezone.utc).isoformat()
            self._resources[resource_id] = res
            if res.assigned_request_id:
                try:
                    self.mark_arrived(res.assigned_request_id, actor=actor)
                except ValueError:
                    pass
        elif action == "done":
            if res.assigned_request_id:
                try:
                    self.complete_request(res.assigned_request_id, actor=actor)
                except ValueError:
                    pass
            res = self._resources[resource_id]
            res.status = ResourceStatus.RETURNING
            res.simulated = False
            res.updated_at = datetime.now(timezone.utc).isoformat()
            self._resources[resource_id] = res
        elif action == "available":
            # "Back in pool" never completes a case. An unfinished case goes back to the queue
            # (status new, team unassigned, seats returned) so a coordinator can send someone else.
            if res.assigned_request_id:
                current = self._requests.get(res.assigned_request_id)
                if current and current.status in (
                    RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS
                ):
                    self._requeue_request(current, res, actor=actor)
            res = self._resources[resource_id]
            res.assigned_request_id = None
            res.simulated = False
            res.status = ResourceStatus.AVAILABLE if res.capacity_remaining > 0 else ResourceStatus.DEPLETED
            res.updated_at = datetime.now(timezone.utc).isoformat()
            self._resources[resource_id] = res
        else:
            raise ValueError(f"Unknown team action {action}")
        self.record_audit(actor=actor, action="team_confirm", target=resource_id, after={"action": action, "status": res.status.value})
        return res

    def _requeue_request(self, req: StoredRequest, res: StoredResource, actor: str = "team") -> None:
        before = req.model_dump()
        amount = req.reserved_people or req.people_count or 1
        req.status = RequestStatus.NEW
        req.assigned_resource_id = None
        req.reserved_people = None
        if "requeued" not in req.flags:
            req.flags.append("requeued")
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        for match in self._matches.values():
            if match.request_id == req.id and match.resource_id == res.id and match.state == MatchState.APPROVED:
                match.state = MatchState.REJECTED
                match.rejected_reason = "Team returned to the pool before finishing"
        res.capacity_remaining = min(res.capacity_total, res.capacity_remaining + amount)
        self.record_audit(actor=actor, action="status_change", target=req.id, before=before,
                          after={**req.model_dump(), "reason": "team back in pool, case re-queued"})

    def load_seed_resources(self, yaml_path: Optional[str] = None, only_ids: Optional[Iterable[str]] = None) -> int:
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
        wanted = set(only_ids) if only_ids is not None else None
        for item in data.get("resources", []):
            if wanted is not None and item.get("id") not in wanted:
                continue
            res = StoredResource(
                id=item["id"],
                event_id=item.get("event_id", data.get("event_id", "event_kerala_flood")),
                pack_id=item.get("pack_id", data.get("scenario_pack", "flood")),
                kind=ResourceKind(item["kind"]),
                name=item["name"],
                name_hi=item.get("name_hi"),
                ward_id=item["ward_id"],
                lat=float(item["lat"]),
                lng=float(item["lng"]),
                supplies=item.get("supplies") or {},
                capacity_total=int(item["capacity_total"]),
                capacity_remaining=int(item.get("capacity_remaining", item["capacity_total"])),
                status=ResourceStatus(item.get("status", "available")),
                location_updated_at=item.get("location_updated_at") or datetime.now(timezone.utc).isoformat(),
                assigned_request_id=item.get("assigned_request_id"),
                area_name=item.get("area_name"),
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

    def list_matches(self) -> List[StoredMatch]:
        return list(self._matches.values())

    def approve_match(self, match_id: str, approved_by: str = "coordinator", allow_overcommit: bool = False) -> StoredMatch:
        # Recheck stock and consume it in the same critical section as capacity.
        with self._hold_lock:
            return self._approve_match_locked(match_id, approved_by, allow_overcommit)

    def _approve_match_locked(
        self,
        match_id: str,
        approved_by: str = "coordinator",
        allow_overcommit: bool = False,
    ) -> StoredMatch:
        """Approves dispatch: decrements resource capacity, updates match and request state."""
        match = self._matches.get(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        if match.state == MatchState.APPROVED:
            return match  # An HTTP retry must not consume capacity or supplies twice.
        if match.state != MatchState.PROPOSED:
            raise ValueError("Only a proposed match can be approved")
        req = self._requests.get(match.request_id)
        assigned = self._resources.get(match.resource_id)
        from app.tools.inventory import missing_supplies
        if req and assigned and missing_supplies(req, assigned):
            raise ValueError("Required referral supplies are no longer in stock; choose another team")
        if req and req.assigned_resource_id and req.status in (RequestStatus.DISPATCHED, RequestStatus.IN_PROGRESS):
            raise ValueError("This case already has an assigned team")
        if req and req.merged_into:
            raise ValueError("This case was merged into another case; dispatch that case instead")
        people_needed = req.people_count if (req and req.people_count) else 1

        # A hold already took the seats. Approving dispatches; it does not take them twice.
        assigned_now = self._resources.get(match.resource_id)
        already_held = bool(assigned_now and assigned_now.hold_request_id == (req.id if req else None))
        if already_held:
            before_res = assigned_now.model_dump()
            assigned_now.hold_request_id = None
            assigned_now.hold_amount = 0
            assigned_now.status = ResourceStatus.DISPATCHED
            self.record_audit(
                actor=approved_by,
                action="capacity_reserved",
                target=assigned_now.id,
                before=before_res,
                after={**assigned_now.model_dump(), "confirmed": True},
            )
            is_overcommit = False
        else:
            _, is_overcommit = self.reserve_capacity(
                resource_id=match.resource_id,
                amount=people_needed,
                allow_overcommit=allow_overcommit,
                actor=approved_by,
            )
        assigned = self._resources.get(match.resource_id)
        if assigned and req:
            if req.required_supplies:
                before_supplies = assigned.model_dump()
                for supply, amount in req.required_supplies.items():
                    assigned.supplies[supply] -= amount
                self.record_audit(actor=approved_by, action="supplies_consumed", target=assigned.id,
                                  before=before_supplies, after=assigned.model_dump())
            assigned.assigned_request_id = req.id
            if not assigned.location_updated_at:
                assigned.location_updated_at = assigned.updated_at
            self._resources[assigned.id] = assigned
            if req.lat is not None and req.lng is not None:
                self.begin_simulation(assigned.id, req.lat, req.lng)

        # Other proposals for this case are no longer needed: drop them and free their holds.
        for other in list(self._matches.values()):
            if other.id == match.id or other.request_id != match.request_id or other.state != MatchState.PROPOSED:
                continue
            other_res = self._resources.get(other.resource_id)
            if other_res is not None and other_res.hold_request_id == match.request_id:
                self.release_hold(other.resource_id, actor=approved_by)
            other.state = MatchState.REJECTED
            other.rejected_reason = "Another team was dispatched"
            other.updated_at = datetime.now(timezone.utc).isoformat()

        before = match.model_dump()
        match.state = MatchState.APPROVED
        match.approved_by = approved_by
        match.overcommit = is_overcommit
        match.overcommit_override = allow_overcommit
        match.updated_at = datetime.now(timezone.utc).isoformat()
        self._matches[match_id] = match

        if req:
            before_req = req.model_dump()
            req.status = RequestStatus.DISPATCHED
            req.assigned_resource_id = match.resource_id
            req.reserved_people = people_needed
            req.updated_at = datetime.now(timezone.utc).isoformat()
            self._requests[req.id] = req
            self.record_audit(
                actor=approved_by,
                action="status_change",
                target=req.id,
                before=before_req,
                after=req.model_dump(),
            )

        self.record_audit(
            actor=approved_by,
            action="match_approved",
            target=match_id,
            before=before,
            after=match.model_dump(),
        )
        return match

    def undo_approval(self, match_id: str, actor: str = "coordinator") -> StoredMatch:
        """Undo a dispatch a few seconds after Approve: give back seats and supplies,
        stop the simulated move, put the case back in Waiting. Audited."""
        with self._hold_lock:
            match = self._matches.get(match_id)
            if not match:
                raise ValueError(f"Match {match_id} not found")
            if match.state == MatchState.PROPOSED:
                return match  # retry-safe
            if match.state != MatchState.APPROVED:
                raise ValueError("Only an approved dispatch can be undone")
            req = self._requests.get(match.request_id)
            if req and req.status not in (RequestStatus.DISPATCHED, RequestStatus.APPROVED):
                raise ValueError("The team is already working this case; it cannot be undone")
            res = self._resources.get(match.resource_id)
            amount = (req.reserved_people if req and req.reserved_people else None) or (req.people_count if req and req.people_count else 1)
            if res is not None:
                if res.simulated and res.sim_origin_lat is not None and res.sim_origin_lng is not None:
                    res.lat, res.lng = res.sim_origin_lat, res.sim_origin_lng
                res.simulated = False
                res.sim_step = 0
                if req and req.required_supplies:
                    for supply, n in req.required_supplies.items():
                        res.supplies[supply] = res.supplies.get(supply, 0) + n
                if res.assigned_request_id == match.request_id:
                    res.assigned_request_id = None
                self._resources[res.id] = res
                self.release_capacity(res.id, amount, actor=actor)
            # Re-open the other offers this approval had closed, so Change still works.
            for other in self._matches.values():
                if (other.id != match.id and other.request_id == match.request_id
                        and other.state == MatchState.REJECTED
                        and other.rejected_reason == "Another team was dispatched"):
                    other.state = MatchState.PROPOSED
                    other.rejected_reason = None
                    other.updated_at = datetime.now(timezone.utc).isoformat()
            before = match.model_dump()
            match.state = MatchState.PROPOSED
            match.approved_by = None
            match.updated_at = datetime.now(timezone.utc).isoformat()
            self._matches[match_id] = match
            if req:
                before_req = req.model_dump()
                req.status = RequestStatus.MATCHED
                req.assigned_resource_id = None
                req.reserved_people = None
                req.updated_at = match.updated_at
                self._requests[req.id] = req
                self.record_audit(actor=actor, action="status_change", target=req.id, before=before_req, after=req.model_dump())
            self.record_audit(actor=actor, action="match_undone", target=match_id, before=before, after=match.model_dump())
            return match

    def mark_arrived(self, request_id: str, actor: str = "coordinator") -> StoredRequest:
        """Coordinator marks the team on scene. Audited. Does not change capacity."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Request {request_id} not found")
        if req.status not in (RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS):
            raise ValueError(f"Request {request_id} is not dispatched")
        before = req.model_dump()
        req.status = RequestStatus.IN_PROGRESS
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        self.record_audit(actor=actor, action="status_change", target=req.id, before=before, after=req.model_dump())
        resource_id = req.assigned_resource_id
        res = self._resources.get(resource_id) if resource_id else None
        if res:
            res.simulated = False
            res.status = ResourceStatus.ON_SCENE
            if req.lat is not None and req.lng is not None:
                res.lat = req.lat
                res.lng = req.lng
            res.location_updated_at = req.updated_at
            res.updated_at = req.updated_at
            self._append_trail(res)
            self._resources[res.id] = res
        return req

    def complete_request(self, request_id: str, actor: str = "coordinator") -> StoredRequest:
        """Marks the case completed and releases the reserved seats back to the team."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Request {request_id} not found")
        if req.status in (RequestStatus.COMPLETED, RequestStatus.RESOLVED, RequestStatus.CLOSED):
            return req
        if req.status not in (RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS):
            raise ValueError(f"Request {request_id} is not dispatched")

        before = req.model_dump()
        resource_id = req.assigned_resource_id
        amount = req.reserved_people or req.people_count or 1
        req.status = RequestStatus.COMPLETED
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        self.record_audit(actor=actor, action="status_change", target=req.id, before=before, after=req.model_dump())

        if resource_id and resource_id in self._resources:
            self._resources[resource_id].simulated = False
            self.release_capacity(resource_id, amount, actor=actor)
            still_out = any(
                other.assigned_resource_id == resource_id
                and other.id != req.id
                and other.status in (RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS)
                for other in self._requests.values()
            )
            res = self._resources[resource_id]
            if still_out and res.capacity_remaining > 0:
                res.status = ResourceStatus.DISPATCHED
            elif res.capacity_remaining <= 0:
                res.status = ResourceStatus.DEPLETED
            else:
                res.assigned_request_id = None
            if not still_out:
                res.assigned_request_id = None
            self._resources[resource_id] = res
        return req

    def dismiss_hoax(self, request_id: str, actor: str = "coordinator", reason: str | None = None) -> StoredRequest:
        """Coordinator confirms a flagged report is a hoax: close it. Nothing is sent; the audit log keeps it."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Request {request_id} not found")
        if req.status in (RequestStatus.DISPATCHED, RequestStatus.APPROVED, RequestStatus.IN_PROGRESS):
            raise ValueError(f"Request {request_id} is already dispatched")
        before = req.model_dump()
        req.status = RequestStatus.DISMISSED_HOAX
        req.flags = sorted(set((req.flags or []) + ["dismissed_hoax"]))
        word = (reason or "").strip().split()
        if word:
            req.hoax_reason = word[0][:40]
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        self.record_audit(actor=actor, action="dismiss_hoax", target=req.id, before=before, after=req.model_dump())
        return req

    def close_as_info(self, request_id: str, actor: str = "coordinator") -> StoredRequest:
        """Close a report that needs no team. It is not a rescue and not a dispatch."""
        req = self._requests.get(request_id)
        if not req:
            raise ValueError(f"Request {request_id} not found")
        if req.status in (
            RequestStatus.DISPATCHED,
            RequestStatus.APPROVED,
            RequestStatus.IN_PROGRESS,
            RequestStatus.COMPLETED,
        ):
            raise ValueError(f"Request {request_id} is already with a team")
        if req.status == RequestStatus.INFO_CLOSED:
            return req
        before = req.model_dump()
        req.status = RequestStatus.INFO_CLOSED
        req.flags = sorted(set((req.flags or []) + ["info_closed"]))
        req.updated_at = datetime.now(timezone.utc).isoformat()
        self._requests[req.id] = req
        self.record_audit(actor=actor, action="close_info", target=req.id, before=before, after=req.model_dump())
        return req

    def reject_match(
        self, match_id: str, reason: str, actor: str = "coordinator"
    ) -> StoredMatch:
        match = self._matches.get(match_id)
        if not match:
            raise ValueError(f"Match {match_id} not found")

        # Release only this case's hold. Another case may hold the same team.
        held = self._resources.get(match.resource_id)
        if held is not None and held.hold_request_id == match.request_id:
            self.release_hold(match.resource_id, actor=actor)
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

    def load_seed_incidents(self, yaml_path: Optional[str] = None, pack_id: str = "flood", only_ids: Optional[Iterable[str]] = None) -> int:
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
        wanted = set(only_ids) if only_ids is not None else None
        for item in data.get("incidents", []):
            if wanted is not None and item.get("id") not in wanted:
                continue
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
                translations_map: Dict[str, str] = {}
                en_text = None
                hi_text = None
                for sr in sample_reports:
                    s_lang = sr.get("lang")
                    s_txt = sr.get("text")
                    if not s_lang or not s_txt or s_lang == "ta":
                        continue
                    translations_map[s_lang] = s_txt
                    if s_lang == "en":
                        en_text = s_txt
                    elif s_lang == "hi":
                        hi_text = s_txt
                # The desk reads English. One seeded case keeps its Hindi line.
                show_hindi = item.get("id") == "INC-001"
                raw_text = hi_text if show_hindi and hi_text else en_text
                ai_translation = en_text or item.get("description", "")
                if not raw_text:
                    raw_text = next((sr.get("text") for sr in sample_reports if sr.get("lang") not in (None, "ta")), None)
                if not ai_translation:
                    ai_translation = item.get("description", "")
                if "en" not in translations_map and ai_translation:
                    translations_map["en"] = ai_translation
                if show_hindi and hi_text:
                    translations_map["hi"] = hi_text

                flags_list = list(item.get("flags", []))

                minutes_ago = count % 50
                stamp = (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()
                from app.tools.scenario_loader import scenario_registry
                pack = scenario_registry.get_scenario(item.get("pack_id") or pack_id)
                requirements = (pack.routing_profiles.get(item.get("routing_profile"), {}) if pack else {})
                req = StoredRequest(
                    required_supplies=dict(requirements),
                    routing_note=item.get("routing_note"),
                    id=item["id"],
                    pack_id=item.get("pack_id") or pack_id,
                    type=IncidentType(item.get("type", "rescue")),
                    # Place is the named spot only (landmark), never the whole description.
                    place_text=_seed_place(item),
                    ward_id=_seed_ward(item),
                    lat=(float(item["lat"]) if item.get("lat") is not None else None),
                    lng=(float(item["lng"]) if item.get("lng") is not None else None),
                    people_count=(int(item["people"]) if item.get("people") else None),
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
                    created_at=stamp,
                    updated_at=stamp,
                )
                # A seed head count is kept only when the report text itself states it; otherwise unknown.
                import re as _re
                _words = {1: "one|a|an|my|single", 2: "two|couple", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
                _txt = (raw_text or "").lower()
                _n = req.people_count
                if _n and not (_re.search(rf"(?<![\d.]){_n}(?![\d.])", _txt) or (_n in _words and _re.search(rf"\b({_words[_n]})\b", _txt))):
                    req.people_count = None
                urg_res = scoring_engine.compute_urgency(req)
                req.urgency_score = urg_res.score
                req.urgency_reason = urg_res.reason

                # No invented merges: INC-001 stands alone until a real duplicate report joins it.
                if req.people_count is None and _re.search(r"\b(?:my |an |a |one )?(?:elderly )?(?:father|mother|grandmother|grandfather|patient|son|daughter|husband|wife|man|woman|person)\b", _txt):
                    req.people_count = 1
                    if "count_provisional" not in req.flags:
                        req.flags.append("count_provisional")
                from app.api.public import public_code_for as _pc
                req.public_code = req.public_code or _pc(req.id)
                _u = scoring_engine.compute_urgency(req)
                req.urgency_score, req.urgency_reason = _u.score, _u.reason
                self._requests[req.id] = req
                count += 1
            except Exception as e:
                logger.warning("Error loading seed incident %s: %s", item.get("id"), e)
        logger.info("Loaded %d synthetic seed incidents into storage.", count)
        return count

    def reset_demo(self) -> Dict[str, Any]:
        """Clear in-memory cases and reload the small demo. The audit log stays append-only."""
        return self._reload_seed("small")

    def load_full_scenario(self) -> Dict[str, Any]:
        """Reload the full flood pack. Benchmark files are not involved."""
        return self._reload_seed("full")

    def _reload_seed(self, mode: str) -> Dict[str, Any]:
        self._reports.clear()
        self._requests.clear()
        self._clusters.clear()
        self._resources.clear()
        self._matches.clear()
        self._idempotent.clear()
        from app.tools.ratelimit import rate_limiter
        rate_limiter.reset()
        if mode == "full":
            resources = self.load_seed_resources()
            incidents = self.load_seed_incidents()
            packs = self.load_scenario_pack_seeds()
            demo = None
            if settings.DEMO_MODE:
                from app.tools.demo_seed import load_demo_pack
                demo = load_demo_pack(self)
                from app.tools.demo_cases import load_demo_cases
                load_demo_cases(self)
        else:
            resources = self.load_seed_resources(only_ids=SMALL_TEAM_IDS)
            incidents = self.load_seed_incidents(only_ids=SMALL_CASE_IDS)
            packs = 0
            demo = None
            if settings.DEMO_MODE:
                from app.tools.demo_cases import load_demo_cases
                incidents += load_demo_cases(self)
                resources = len(self._resources)
        _attach_recorded(self)
        self.record_audit(
            actor="reset_demo",
            action="demo_reset" if mode == "small" else "demo_full",
            target="storage",
            after={"resources": resources, "incidents": incidents, "scenario_packs": packs, "seed": mode},
        )
        try:
            import sys
            import threading
            from app.agents.sitrep import prewarm_sitrep

            if "pytest" not in sys.modules:
                threading.Thread(target=prewarm_sitrep, daemon=True).start()
        except Exception:
            pass
        return {"resources": resources, "incidents": incidents, "scenario_packs": packs, "demo": demo, "seed": mode}

    def load_missing_scenario(self, pack_id: str) -> None:
        """Append missing seed rows; switching views never replenishes used stock."""
        from pathlib import Path
        import yaml
        base = Path(__file__).resolve().parents[4] / "data" / "synthetic" / pack_id
        for name, collection, loader in (
            ("seeds.yaml", "incidents", self.load_seed_incidents),
            ("resources.yaml", "resources", self.load_seed_resources),
        ):
            path = base / name
            if not path.exists():
                continue
            rows = yaml.safe_load(path.read_text(encoding="utf-8"))[collection]
            exists = self.get_request if collection == "incidents" else self.get_resource
            kwargs = {"pack_id": pack_id} if collection == "incidents" else {}
            loader(str(path), only_ids=[row["id"] for row in rows if exists(row["id"]) is None], **kwargs)

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
            resource_path = os.path.join(base_dir, "data", "synthetic", scenario.id, "resources.yaml")
            if os.path.exists(resource_path):
                self.load_seed_resources(resource_path)
        return loaded


def _attach_recorded(storage) -> None:
    try:
        from app.llm.replay_seed import attach_recorded_ai

        attach_recorded_ai(storage)
    except Exception as exc:  # recordings are optional
        logger.warning("Could not attach recorded Gemini readings: %s", exc)


def _seed_place(item: dict) -> Optional[str]:
    """Short place for a seeded case: its landmark name, else a 'near X' span, else None."""
    import re as _re
    from app.tools.gazetteer import landmark_name
    name = landmark_name(item.get("landmark_id"))
    if name:
        return name
    m = _re.search(r"\b(?:near|at|in)\s+((?:[A-Z][\w'-]+\s?){1,4})", item.get("description") or "")
    return m.group(1).strip() if m else None


def _seed_ward(item: dict) -> Optional[str]:
    """Ward from the case's coordinates; falls back to the seed ward only when there are none."""
    from app.tools.gazetteer import ward_for_point
    lat, lng = item.get("lat"), item.get("lng")
    if lat is not None and lng is not None:
        return ward_for_point(float(lat), float(lng))
    return item.get("ward_id")



# Singleton instance
storage_service = StorageService()
# Auto-load seed resources and incidents
try:
    if active_seed_mode() == "full":
        storage_service.load_seed_resources()
        storage_service.load_seed_incidents()
        storage_service.load_scenario_pack_seeds()
        _attach_recorded(storage_service)
        if settings.DEMO_MODE:
            from app.tools.demo_seed import load_demo_pack
            load_demo_pack(storage_service)
    else:
        storage_service.load_seed_resources(only_ids=SMALL_TEAM_IDS)
        storage_service.load_seed_incidents(only_ids=SMALL_CASE_IDS)
        _attach_recorded(storage_service)
        if settings.DEMO_MODE:
            # Cases live in memory: every cold start gets the same believable synthetic board.
            from app.tools.demo_cases import load_demo_cases
            load_demo_cases(storage_service)
except Exception:
    pass


DEMO_CHECKIN_STALE_MIN = 90


def simulate_demo_checkins(resources, now=None):
    """DEMO_MODE only: synthetic teams 'check in' so Free/Busy reflect a live desk.

    A synthetic team whose last check-in is older than 90 min gets a fresh simulated
    check-in 2-26 min ago and is flagged simulated=True. About one in five teams is left
    alone so the 'Not updated' state still shows. Real (non-synthetic) teams are never touched.
    """
    import zlib
    now = now or datetime.now(timezone.utc)
    changed = 0
    for res in resources:
        if not getattr(res, "synthetic", False):
            continue
        h = zlib.crc32(res.id.encode("utf-8"))
        if h % 5 == 0:
            # About one in five synthetic teams shows a late check-in (simulated), so the
            # 'Not updated' state is visible. Done once; flagged simulated.
            if not getattr(res, 'simulated', False):
                res.location_updated_at = (now - timedelta(minutes=150 + h % 60)).isoformat()
                res.simulated = True
            continue
        try:
            last = datetime.fromisoformat(str(res.location_updated_at).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            last = None
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is not None and (now - last) <= timedelta(minutes=DEMO_CHECKIN_STALE_MIN):
            continue
        res.location_updated_at = (now - timedelta(minutes=2 + h % 25)).isoformat()
        res.simulated = True
        changed += 1
    return changed

