import hashlib
import re
from typing import Dict, List, Tuple


def normalize_text_for_hash(text: str) -> str:
    """Normalizes text by lowercasing and stripping punctuation and excess whitespace."""
    cleaned = re.sub(r"[^\w\s\u0900-\u097F]", "", text.lower())
    return " ".join(cleaned.split())


def compute_hash_dedupe(messages: List[Dict]) -> List[Dict]:
    """Naive hash-dedupe baseline: flags duplicates if exact normalized text was seen before."""
    seen_hashes: set[str] = set()
    decisions = []
    for msg in messages:
        norm = normalize_text_for_hash(msg["text"])
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        is_dup = h in seen_hashes
        seen_hashes.add(h)
        decisions.append({
            "id": msg["id"],
            "decision": "duplicate" if is_dup else "new",
            "hash": h[:8]
        })
    return decisions
