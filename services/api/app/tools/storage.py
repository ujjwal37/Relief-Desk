import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from app.config import settings
from app.models.firestore_models import (
    StoredReport,
    StoredRequest,
    StoredCluster,
    StoredResource,
    StoredMatch,
    AuditEntry,
    RequestStatus,
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
    ) -> StoredReport:
        """Stores incoming report raw immediately so nothing is ever lost."""
        report_id = f"rep_{uuid.uuid4().hex[:10]}"
        report = StoredReport(
            id=report_id,
            event_id=event_id,
            pack_id=pack_id,
            channel=channel,
            lang=lang,
            raw_text=raw_text,
            source_id=source_id,
            trust_level=trust_level,
            flags=flags or [],
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

    def list_reports(self) -> List[StoredReport]:
        return list(self._reports.values())

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

    # --- Resources DAO ---
    def save_resource(
        self, resource: StoredResource, actor: str = "system", audit: bool = True
    ) -> StoredResource:
        try:
            before = (
                self._resources[resource.id].model_dump(mode="json")
                if resource.id in self._resources
                else None
            )
            resource.updated_at = datetime.now(timezone.utc).isoformat()
            self._resources[resource.id] = resource
            if audit:
                self.record_audit(
                    actor=actor,
                    action="resource_updated" if before else "resource_created",
                    target=resource.id,
                    before=before,
                    after=resource.model_dump(mode="json"),
                )
            return resource
        except Exception:
            logger.exception("Failed to save resource %s", resource.id)
            raise

    def get_resource(self, resource_id: str) -> Optional[StoredResource]:
        return self._resources.get(resource_id)

    def list_resources(self) -> List[StoredResource]:
        return list(self._resources.values())

    # --- Matches DAO ---
    def save_match(self, match: StoredMatch) -> StoredMatch:
        try:
            match.updated_at = datetime.now(timezone.utc).isoformat()
            self._matches[match.id] = match
            return match
        except Exception:
            logger.exception("Failed to save match %s", match.id)
            raise

    def get_match(self, match_id: str) -> Optional[StoredMatch]:
        return self._matches.get(match_id)

    def list_matches(self, request_id: Optional[str] = None) -> List[StoredMatch]:
        matches = list(self._matches.values())
        if request_id:
            return [m for m in matches if m.request_id == request_id]
        return matches

    def mirror_resource_transaction(self, resource: StoredResource) -> None:
        """Persist a resource inside a Firestore transaction when the emulator is up.

        The in-memory lock is the transaction for local tests. This mirror makes
        the committed capacity document atomic on Firestore as well.
        """
        client = self._firestore_client
        if client is None:
            return
        try:
            from google.cloud import firestore  # type: ignore

            ref = client.collection("resources").document(resource.id)
            transaction = client.transaction()
            payload = resource.model_dump(mode="json")

            @firestore.transactional
            def _write(txn, doc_ref, body):  # type: ignore[no-untyped-def]
                txn.set(doc_ref, body)

            _write(transaction, ref, payload)
            logger.info("Firestore capacity transaction committed for %s", resource.id)
        except Exception:
            logger.exception("Firestore capacity transaction failed for %s", resource.id)


# Singleton instance
storage_service = StorageService()
