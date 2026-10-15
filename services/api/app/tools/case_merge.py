"""Fold one open case into another. Auto-merge and the coordinator's Merge button share this."""
from __future__ import annotations

from typing import List, Optional

from app.models.firestore_models import ReportQuote, StoredRequest
from app.tools.nlu_rules import counts_note, span_upper
from app.tools.storage import storage_service


def _spans(req: StoredRequest) -> List[str]:
    ordered: List[str] = []
    for span in list(req.count_spans or []):
        if span and span not in ordered:
            ordered.append(span)
    if req.people_span and req.people_span not in ordered:
        ordered.append(req.people_span)
    return ordered


def _quotes(req: StoredRequest) -> List[ReportQuote]:
    if req.report_quotes:
        return list(req.report_quotes)
    text = (req.raw_text or "").strip()
    if not text:
        return []
    report_id = req.report_ids[0] if req.report_ids else req.id
    return [ReportQuote(report_id=report_id, text=text, people_span=req.people_span)]


_HAZARD_RANK = {"none": 0, "unknown": 1, "stranded": 2, "injury": 3, "water_rising": 4}


def _value(item) -> str:
    return str(getattr(item, "value", item))


def _status(req: StoredRequest) -> str:
    return _value(req.status)


def fold_case(
    primary_id: str,
    secondary_id: str,
    evidence: Optional[List[str]] = None,
    merged_by: str = "coordinator",
) -> StoredRequest:
    """Keep the primary case. The secondary leaves the queue and its reports follow the primary."""
    with storage_service._submit_lock:
        return _fold_locked(primary_id, secondary_id, evidence, merged_by)


def _fold_locked(
    primary_id: str,
    secondary_id: str,
    evidence: Optional[List[str]],
    merged_by: str,
) -> StoredRequest:
    primary = storage_service.get_request(primary_id)
    secondary = storage_service.get_request(secondary_id)
    if primary is None:
        raise ValueError(f"Primary request '{primary_id}' not found")
    if secondary is None:
        raise ValueError(f"Secondary request '{secondary_id}' not found")
    if primary_id == secondary_id:
        raise ValueError("A case cannot be merged into itself")
    if secondary.merged_into == primary_id:
        return primary
    if secondary.merged_into:
        raise ValueError(f"Case '{secondary_id}' is already merged into '{secondary.merged_into}'")
    if primary.merged_into:
        raise ValueError(f"Case '{primary_id}' is already merged into '{primary.merged_into}'")
    busy = {"approved", "dispatched", "in_progress"}
    if _status(secondary) in busy and _status(primary) in busy:
        raise ValueError("Both cases already have a team. Complete one before merging.")
    if _status(secondary) in busy:
        # Keep the case that has the team as the survivor, so its team is never left on a hidden case.
        primary, secondary = secondary, primary

    quotes = _quotes(primary)
    seen = {quote.report_id for quote in quotes}
    for quote in _quotes(secondary):
        if quote.report_id in seen:
            continue
        quotes.append(quote)
        seen.add(quote.report_id)
    primary.report_quotes = quotes

    spans = _spans(primary)
    for span in _spans(secondary):
        if span not in spans:
            spans.append(span)
    if not spans:
        for count in (primary.people_count, secondary.people_count):
            label = str(count) if count else ""
            if label and label not in spans:
                spans.append(label)
    primary.count_spans = spans
    primary.people_span = primary.people_span or (spans[0] if spans else None)
    primary.count_note = counts_note(spans)
    uppers = [span_upper(span) for span in spans if span_upper(span)]
    uppers.extend(count for count in (primary.people_count, secondary.people_count) if count)
    if uppers:
        primary.people_count = max(uppers)

    for report_id in secondary.report_ids:
        if report_id not in primary.report_ids:
            primary.report_ids.append(report_id)
    # The merged case must keep every vulnerable person and the worst hazard any report described.
    for name, value in secondary.vulnerable.model_dump().items():
        if value:
            setattr(primary.vulnerable, name, True)
    if _HAZARD_RANK.get(_value(secondary.hazard), 0) > _HAZARD_RANK.get(_value(primary.hazard), 0):
        primary.hazard = secondary.hazard
    for flag in secondary.flags or []:
        if flag not in primary.flags and flag not in ("hoax", "hoax_or_flood"):
            primary.flags.append(flag)
    # Older report sets the waiting clock.
    if (secondary.created_at or "") and (secondary.created_at < (primary.created_at or secondary.created_at)):
        primary.created_at = secondary.created_at

    primary.merged_count = (primary.merged_count or 1) + (secondary.merged_count or 1)
    secondary.merged_into = primary.id
    secondary.merged_count = primary.merged_count
    secondary.possible_duplicate = None
    primary.possible_duplicate = None

    for report in storage_service.list_reports():
        if report.request_id == secondary.id or report.case_id == secondary.id or report.id in secondary.report_ids:
            report.request_id = primary.id
            report.case_id = primary.id
            report.joined_existing = True

    from app.tools.scoring import scoring_engine

    scored = scoring_engine.compute_urgency(primary)
    primary.urgency_score = scored.score
    primary.urgency_reason = scored.reason
    storage_service.save_request(secondary, actor=merged_by)
    storage_service.save_request(primary, actor=merged_by)
    storage_service.create_cluster(
        request_ids=[primary.id, secondary.id],
        evidence=list(evidence or ["Coordinator merged the reports"]),
        merged_by=merged_by,
    )
    return storage_service.get_request(primary.id) or primary
