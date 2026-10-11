import hashlib
import re
from typing import Dict, List


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


def keyword_extract_baseline(text: str) -> Dict:
    """Keyword-based extraction baseline to show what LLM language understanding adds."""
    t = text.lower()

    if any(k in t for k in ["rescue", "fas gaye", "stranded", "bachao", "boat", "dub raha", "doob", "paani"]):
        itype = "rescue"
    elif any(k in t for k in ["medical", "doctor", "dawai", "medicine", "injury", "chot", "bimar", "bleeding"]):
        itype = "medical"
    elif any(k in t for k in ["food", "khana", "ration", "bhookh", "water bottle"]):
        itype = "food"
    elif any(k in t for k in ["shelter", "rahat", "chhat", "stay"]):
        itype = "shelter"
    elif any(k in t for k in ["dog", "kutta", "bite", "rabies"]):
        itype = "animal_attack"
    else:
        itype = "other"

    ward_match = re.search(r"ward\s*(\d+)", t)
    ward_id = f"ward_{ward_match.group(1)}" if ward_match else None

    nums = re.findall(r"\b(\d+)\s*(?:log|people|person|members|family)?\b", t)
    people = int(nums[0]) if nums else 1

    vuln = {
        "child": any(k in t for k in ["child", "bacha", "bacche", "kid", "baby"]),
        "elderly": any(k in t for k in ["elderly", "boodhe", "bujurg", "old", "dada", "dadi"]),
        "disabled": any(k in t for k in ["disabled", "divyang", "wheelchair"]),
        "pregnant": any(k in t for k in ["pregnant", "garbhvati"]),
        "medical_need": any(k in t for k in ["insulin", "oxygen", "bp", "heart", "dialysis", "medical", "dawai"]),
    }

    return {
        "type": itype,
        "ward_id": ward_id,
        "people": people,
        "vulnerable": vuln,
    }
