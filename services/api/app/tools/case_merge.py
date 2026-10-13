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

    storage_service.save_request(secondary, actor=merged_by)
    storage_service.save_request(primary, actor=merged_by)
    storage_service.create_cluster(
        request_ids=[primary.id, secondary.id],
        evidence=list(evidence or ["Coordinator merged the reports"]),
        merged_by=merged_by,
    )
    return storage_service.get_request(primary.id) or primary
