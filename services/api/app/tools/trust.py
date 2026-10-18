import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from app.models.firestore_models import StoredRequest, StoredReport, RequestStatus

logger = logging.getLogger("relief_desk.trust")

TRUST_CONFIDENCE_WEIGHTS = {
    "official": 1.0,
    "verified_volunteer": 0.95,
    "registered": 0.85,
    "anonymous": 0.70,
}


def score_source_trust(trust_level: str) -> float:
    """Returns trust confidence multiplier for a given source tier."""
    return TRUST_CONFIDENCE_WEIGHTS.get(trust_level.lower(), 0.70)


def evaluate_stale_status(
    req: StoredRequest,
    stale_threshold_minutes: int = 120,
    current_time: Optional[datetime] = None,
) -> bool:
    """If an open request has not received updates/verification for > threshold,
    flags it as stale and transitions status to needs_recheck. NEVER deletes."""
    now = current_time or datetime.now(timezone.utc)
    try:
        updated_dt = datetime.fromisoformat(req.updated_at)
        elapsed_min = (now - updated_dt).total_seconds() / 60.0
    except Exception:
        elapsed_min = 0.0

    if elapsed_min > stale_threshold_minutes and req.status in (RequestStatus.NEW, RequestStatus.MATCHED):
        if "stale" not in req.flags:
            req.flags.append("stale")
        req.status = RequestStatus.NEEDS_RECHECK
        req.updated_at = now.isoformat()
        logger.info("Request %s flagged stale (%dm > %dm) -> status set to needs_recheck", req.id, int(elapsed_min), stale_threshold_minutes)
        return True
    return False


import re

VIRAL_HOAX_PHRASES = (
    "forward this to 10 groups",
    "forward to all",
    "forward-to-all",
    "forward this to all",
    "share widely",
    "share-widely",
    "share this widely",
    "army says",
    "army has said",
    "nasa announced",
    "free helicopter rescue call this number",
    "100% verified news share fast",
    "free money",
    "bit.ly",
    "win iphone",
    "send otp",
)


def hoax_phrases(text: str) -> List[str]:
    clean = " ".join((text or "").lower().split())
    norm = re.sub(r"[-_:]+", " ", clean)
    hits = []
    for phrase in VIRAL_HOAX_PHRASES:
        if phrase in clean or phrase in norm:
            hits.append(phrase)

    has_dam = ("dam broke" in clean or "dam broke" in norm or "dam has broken" in clean or "dam has broken" in norm)
    has_co_cue = any(cue in clean or cue in norm for cue in ("forward", "share", "everyone evacuate"))
    if has_dam and has_co_cue:
        if "dam broke" in clean or "dam broke" in norm:
            hits.append("dam broke")
        if "dam has broken" in clean or "dam has broken" in norm:
            hits.append("dam has broken")

    return hits


def hoax_reason_for(text: str) -> Optional[str]:
    """One plain sentence a coordinator can read. Empty when nothing matched."""
    hits = hoax_phrases(text)
    if not hits:
        return None
    return f"Known hoax / spam phrase: {hits[0]}"


def hoax_score_for(text: str) -> float:
    """0 when the text has no known spam phrase, else at least 0.9."""
    hits = len(hoax_phrases(text))
    if hits <= 0:
        return 0.0
    return min(1.0, 0.7 + 0.1 * hits)


def detect_hoax_or_flood(
    existing_reports: List[StoredReport],
    new_raw_text: str,
    source_id: str,
    burst_threshold: int = 3,
) -> List[str]:
    """Detects copy-paste floods or hoax patterns.
    Flags only; never auto-deletes."""
    flags: List[str] = []
    clean_new = " ".join(new_raw_text.lower().split())

    # Count how many identical texts from this or other sources
    match_count = 0
    for r in existing_reports:
        clean_existing = " ".join(r.raw_text.lower().split())
        if clean_new == clean_existing:
            match_count += 1

    if match_count >= burst_threshold:
        flags.append("hoax_or_flood")
        logger.warning("Detected %d duplicate copies of message. Flagged hoax_or_flood.", match_count)

    # Check for known viral hoax keywords
    if hoax_score_for(new_raw_text) >= 0.5:
        flags.append("hoax")

    return flags


def detect_conflict_in_cluster(requests: List[StoredRequest]) -> bool:
    """Flags conflicting information among merged reports (e.g. stranded vs no hazard)."""
    if len(requests) < 2:
        return False

    hazards = {r.hazard for r in requests}
    # Conflict if one says water_rising and another says none
    if "water_rising" in hazards and "none" in hazards:
        for r in requests:
            if "conflict" not in r.flags:
                r.flags.append("conflict")
        return True
    return False
