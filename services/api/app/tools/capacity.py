"""Capacity reserve and release.

Approve is the only path that decrements capacity. When the request needs
more people than the resource has left, the call is refused with an
overcommit warning until the coordinator sends an explicit override.
That override is audited. Nothing here auto-dispatches.
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from threading import Lock
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.firestore_models import (
    MatchState,
    RequestStatus,
    ResourceStatus,
    StoredMatch,
    StoredRequest,
    StoredResource,
)
from app.tools.scoring import is_type_compatible, match_score, people_demand
from app.tools.storage import StorageService, storage_service

logger = logging.getLogger("relief_desk.capacity")

SEED_PATH = Path(__file__).resolve().parents[4] / "data" / "resources" / "seed.json"
CALL_112 = "In an emergency call 112"


class CapacityError(Exception):
    """Base error for capacity decisions. Routers map these to HTTP status codes."""


class ResourceNotFound(CapacityError):
    def __init__(self, resource_id: str):
        self.resource_id = resource_id
        super().__init__(f"Resource '{resource_id}' not found")


class RequestNotFound(CapacityError):
    def __init__(self, request_id: str):
        self.request_id = request_id
        super().__init__(f"Request '{request_id}' not found")


class MatchNotFound(CapacityError):
    def __init__(self, match_id: str):
        self.match_id = match_id
        super().__init__(f"Match '{match_id}' not found")


class MatchIneligible(CapacityError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class MatchStateError(CapacityError):
    pass


class ResourceUnavailable(CapacityError):
    pass


class CapacityDecision(BaseModel):
    match_id: str
    request_id: str
    resource_id: str
    resource_name: str
    state: MatchState
    overcommit: bool = False
    warning: Optional[str] = None
    requires_override: bool = False
    people_requested: int
    reserved_units: int = 0
    capacity_total: int
    capacity_remaining: int
    audit_action: str
    idempotent: bool = False
    call_112: str = CALL_112


class OvercommitRequired(CapacityError):
    def __init__(self, decision: CapacityDecision):
        self.decision = decision
        super().__init__(decision.warning or "Explicit override is required")


class ResourceSeedFile(BaseModel):
    event_id: str
    pack_id: str
    city: str
    synthetic: bool = True
    note: str = ""
    resources: List[StoredResource] = Field(default_factory=list)


def overcommit_warning(resource_name: str, requested: int, remaining: int) -> str:
    return (
        f"Overcommit warning: request needs {requested} people but {resource_name} "
        f"has {remaining} capacity remaining. Explicit coordinator override is required."
    )


def status_for_remaining(remaining: int) -> ResourceStatus:
    if remaining < 0:
        return ResourceStatus.OVERCOMMITTED
    if remaining == 0:
        return ResourceStatus.DEPLETED
    return ResourceStatus.AVAILABLE


def apply_reserve(remaining: int, amount: int, override: bool) -> tuple[int, bool]:
    """Return (new_remaining, overcommit). Refuse when amount exceeds remaining."""
    if amount < 0:
        raise ValueError("Reserve amount must be >= 0")
    overcommit = amount > remaining
    if overcommit and not override:
        raise ValueError("override required")
    return remaining - amount, overcommit


def apply_release(remaining: int, total: int, amount: int) -> int:
    if amount < 0:
        raise ValueError("Release amount must be >= 0")
    return min(total, remaining + amount)


def load_resource_seed(path: Optional[Path] = None) -> List[StoredResource]:
    seed_path = path or SEED_PATH
    try:
        with open(seed_path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        seed = ResourceSeedFile.model_validate(raw)
        if not seed.synthetic:
            raise ValueError("Resource seed must be marked synthetic")
        resources: List[StoredResource] = []
        for resource in seed.resources:
            resource.event_id = resource.event_id or seed.event_id
            resource.pack_id = resource.pack_id or seed.pack_id
            resource.synthetic = True
            resources.append(resource)
        logger.info("Loaded %d resources from %s", len(resources), seed_path)
        return resources
    except Exception:
        logger.exception("Failed to load resource seed at %s", seed_path)
        raise


def template_explanation(resource_name: str, score: float, breakdown: dict) -> str:
    return (
        f"{resource_name} scores {score}. "
        f"Breakdown dist {breakdown.get('dist', 0)}, "
        f"capacity {breakdown.get('capacity', 0)}, "
        f"urgency {breakdown.get('urgency', 0)}, "
        f"vulnerability {breakdown.get('vuln', 0)}."
    )


class CapacityService:
    def __init__(self, storage: Optional[StorageService] = None):
        self.storage = storage or storage_service
        self._lock = Lock()
        self.ensure_seeded()

    def ensure_seeded(self) -> int:
        try:
            if self.storage.list_resources():
                return 0
            loaded = load_resource_seed()
            for resource in loaded:
                self.storage.save_resource(resource, audit=False)
            logger.info("Seeded %d synthetic resources", len(loaded))
            return len(loaded)
        except Exception:
            logger.exception("Resource seed failed")
            raise

    def list_resources(self) -> List[StoredResource]:
        self.ensure_seeded()
        return self.storage.list_resources()

    def get_resource(self, resource_id: str) -> StoredResource:
        self.ensure_seeded()
        resource = self.storage.get_resource(resource_id)
        if resource is None:
            raise ResourceNotFound(resource_id)
        return resource

    def propose_match(
        self, request_id: str, resource_id: str, actor: str = "coordinator"
    ) -> StoredMatch:
        try:
            request = self.storage.get_request(request_id)
            if request is None:
                raise RequestNotFound(request_id)
            resource = self.get_resource(resource_id)
            scored = match_score(request, resource)
            if not scored.eligible:
                raise MatchIneligible(
                    scored.hard_constraint or "resource is not eligible for this request"
                )
            warning = None
            if scored.overcommit_risk:
                warning = overcommit_warning(
                    resource.name, scored.people_requested, resource.capacity_remaining
                )
            match = StoredMatch(
                id=f"match_{uuid.uuid4().hex[:12]}",
                event_id=request.event_id,
                pack_id=request.pack_id,
                request_id=request.id,
                resource_id=resource.id,
                score=scored.score,
                breakdown=scored.breakdown,
                explanation=template_explanation(resource.name, scored.score, scored.breakdown),
                state=MatchState.PROPOSED,
                overcommit=scored.overcommit_risk,
                warning=warning,
                distance_km=scored.distance_km,
            )
            self.storage.save_match(match)
            self.storage.record_audit(
                actor=actor,
                action="match_proposed",
                target=match.id,
                after=match.model_dump(mode="json"),
            )
            if request.status in (RequestStatus.NEW, RequestStatus.NEEDS_RECHECK):
                self.storage.update_request_status(request.id, RequestStatus.MATCHED, actor=actor)
            logger.info(
                "Proposed match %s request %s resource %s score %s overcommit %s",
                match.id,
                request.id,
                resource.id,
                match.score,
                match.overcommit,
            )
            return match
        except CapacityError:
            raise
        except Exception:
            logger.exception(
                "propose_match failed for request %s resource %s", request_id, resource_id
            )
            raise

    def get_match(self, match_id: str) -> StoredMatch:
        match = self.storage.get_match(match_id)
        if match is None:
            raise MatchNotFound(match_id)
        return match

    def approve_match(
        self, match_id: str, approved_by: str = "coordinator", override: bool = False
    ) -> CapacityDecision:
        try:
            with self._lock:
                decision = self._approve_locked(match_id, approved_by, override)
            logger.info(
                "Approve %s by %s override %s remaining %s",
                match_id,
                approved_by,
                override,
                decision.capacity_remaining,
            )
            return decision
        except CapacityError:
            raise
        except Exception:
            logger.exception("approve_match failed for %s", match_id)
            raise

    def reject_match(
        self, match_id: str, rejected_by: str = "coordinator", reason: str = ""
    ) -> CapacityDecision:
        try:
            with self._lock:
                decision = self._reject_locked(match_id, rejected_by, reason)
            logger.info("Reject %s by %s", match_id, rejected_by)
            return decision
        except CapacityError:
            raise
        except Exception:
            logger.exception("reject_match failed for %s", match_id)
            raise

    def _approve_locked(
        self, match_id: str, approved_by: str, override: bool
    ) -> CapacityDecision:
        match = self.storage.get_match(match_id)
        if match is None:
            raise MatchNotFound(match_id)
        resource = self.storage.get_resource(match.resource_id)
        if resource is None:
            raise ResourceNotFound(match.resource_id)
        request = self.storage.get_request(match.request_id)
        if request is None:
            raise RequestNotFound(match.request_id)

        if match.state == MatchState.APPROVED:
            return self._decision_from_current(
                match, request, resource, audit_action="capacity_reserved", idempotent=True
            )
        if match.state == MatchState.REJECTED:
            raise MatchStateError(f"Match '{match.id}' is rejected and cannot be approved")
        if resource.status == ResourceStatus.OFFLINE:
            raise ResourceUnavailable(f"Resource '{resource.name}' is offline")
        if not is_type_compatible(request, resource.kind):
            raise MatchIneligible("type_incompatible")

        amount = people_demand(request)
        previous_remaining = resource.capacity_remaining
        if amount > previous_remaining and not override:
            warning = overcommit_warning(resource.name, amount, previous_remaining)
            match.overcommit = True
            match.warning = warning
            self.storage.save_match(match)
            self.storage.record_audit(
                actor=approved_by,
                action="overcommit_warning",
                target=match.id,
                before={
                    "match_state": MatchState.PROPOSED.value,
                    "resource_id": resource.id,
                    "capacity_remaining": previous_remaining,
                    "capacity_total": resource.capacity_total,
                    "override": False,
                },
                after={
                    "blocked": True,
                    "requires_override": True,
                    "people_requested": amount,
                    "capacity_remaining": previous_remaining,
                    "warning": warning,
                    "override": False,
                },
            )
            raise OvercommitRequired(
                CapacityDecision(
                    match_id=match.id,
                    request_id=request.id,
                    resource_id=resource.id,
                    resource_name=resource.name,
                    state=MatchState.PROPOSED,
                    overcommit=True,
                    warning=warning,
                    requires_override=True,
                    people_requested=amount,
                    reserved_units=0,
                    capacity_total=resource.capacity_total,
                    capacity_remaining=previous_remaining,
                    audit_action="overcommit_warning",
                )
            )

        new_remaining, overcommit = apply_reserve(previous_remaining, amount, override)
        warning = (
            overcommit_warning(resource.name, amount, previous_remaining) if overcommit else None
        )
        resource.capacity_remaining = new_remaining
        resource.status = status_for_remaining(new_remaining)
        self.storage.save_resource(resource, actor=approved_by, audit=False)
        self.storage.mirror_resource_transaction(resource)

        match.state = MatchState.APPROVED
        match.approved_by = approved_by
        match.overcommit = overcommit
        match.warning = warning
        match.reserved_units = amount
        self.storage.save_match(match)
        action = "capacity_overcommit_override" if overcommit else "capacity_reserved"
        self.storage.record_audit(
            actor=approved_by,
            action=action,
            target=match.id,
            before={
                "match_state": MatchState.PROPOSED.value,
                "resource_id": resource.id,
                "capacity_remaining": previous_remaining,
                "capacity_total": resource.capacity_total,
            },
            after={
                "match_state": MatchState.APPROVED.value,
                "resource_id": resource.id,
                "capacity_remaining": new_remaining,
                "reserved_units": amount,
                "overcommit": overcommit,
                "override": override,
                "approved_by": approved_by,
                "warning": warning,
            },
        )
        if request.status != RequestStatus.APPROVED:
            self.storage.update_request_status(
                request.id, RequestStatus.APPROVED, actor=approved_by
            )
        return CapacityDecision(
            match_id=match.id,
            request_id=request.id,
            resource_id=resource.id,
            resource_name=resource.name,
            state=MatchState.APPROVED,
            overcommit=overcommit,
            warning=warning,
            requires_override=False,
            people_requested=amount,
            reserved_units=amount,
            capacity_total=resource.capacity_total,
            capacity_remaining=new_remaining,
            audit_action=action,
        )

    def _reject_locked(self, match_id: str, rejected_by: str, reason: str) -> CapacityDecision:
        match = self.storage.get_match(match_id)
        if match is None:
            raise MatchNotFound(match_id)
        resource = self.storage.get_resource(match.resource_id)
        if resource is None:
            raise ResourceNotFound(match.resource_id)
        request = self.storage.get_request(match.request_id)
        if request is None:
            raise RequestNotFound(match.request_id)

        if match.state == MatchState.REJECTED:
            return self._decision_from_current(
                match, request, resource, audit_action="match_rejected", idempotent=True
            )

        previous_remaining = resource.capacity_remaining
        released = 0
        action = "match_rejected"
        if match.state == MatchState.APPROVED and match.reserved_units > 0:
            released = match.reserved_units
            resource.capacity_remaining = apply_release(
                previous_remaining, resource.capacity_total, released
            )
            resource.status = status_for_remaining(resource.capacity_remaining)
            self.storage.save_resource(resource, actor=rejected_by, audit=False)
            self.storage.mirror_resource_transaction(resource)
            action = "capacity_released"

        match.state = MatchState.REJECTED
        match.rejected_by = rejected_by
        match.reject_reason = reason
        match.reserved_units = 0
        self.storage.save_match(match)
        self.storage.record_audit(
            actor=rejected_by,
            action=action,
            target=match.id,
            before={
                "resource_id": resource.id,
                "capacity_remaining": previous_remaining,
                "released_units": released,
            },
            after={
                "match_state": MatchState.REJECTED.value,
                "resource_id": resource.id,
                "capacity_remaining": resource.capacity_remaining,
                "reason": reason,
                "rejected_by": rejected_by,
            },
        )
        if action == "capacity_released" and request.status == RequestStatus.APPROVED:
            self.storage.update_request_status(
                request.id, RequestStatus.MATCHED, actor=rejected_by
            )
        return CapacityDecision(
            match_id=match.id,
            request_id=request.id,
            resource_id=resource.id,
            resource_name=resource.name,
            state=MatchState.REJECTED,
            overcommit=match.overcommit,
            warning=match.warning,
            requires_override=False,
            people_requested=people_demand(request),
            reserved_units=0,
            capacity_total=resource.capacity_total,
            capacity_remaining=resource.capacity_remaining,
            audit_action=action,
        )

    def _decision_from_current(
        self,
        match: StoredMatch,
        request: StoredRequest,
        resource: StoredResource,
        audit_action: str,
        idempotent: bool,
    ) -> CapacityDecision:
        action = audit_action
        if match.overcommit and match.state == MatchState.APPROVED:
            action = "capacity_overcommit_override"
        return CapacityDecision(
            match_id=match.id,
            request_id=request.id,
            resource_id=resource.id,
            resource_name=resource.name,
            state=match.state,
            overcommit=match.overcommit,
            warning=match.warning,
            requires_override=False,
            people_requested=people_demand(request),
            reserved_units=match.reserved_units,
            capacity_total=resource.capacity_total,
            capacity_remaining=resource.capacity_remaining,
            audit_action=action,
            idempotent=idempotent,
        )


capacity_service = CapacityService()
