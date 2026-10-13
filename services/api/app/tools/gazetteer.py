import difflib
import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.tools.geo import grid_cell_id

logger = logging.getLogger("relief_desk.gazetteer")

GAZETTEER_FILE = Path(__file__).resolve().parents[4] / "data" / "gazetteer" / "kerala_gazetteer.json"


class GazetteerMatch(BaseModel):
    landmark_id: Optional[str] = None
    landmark_name: Optional[str] = None
    ward_id: Optional[str] = None
    ward_name: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    cell_id: Optional[str] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    matched_alias: Optional[str] = None
    is_low_confidence: bool = False


class Gazetteer:
    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or GAZETTEER_FILE
        self.city: str = "Kerala"
        self.wards: Dict[str, Dict[str, Any]] = {}
        self.landmarks: List[Dict[str, Any]] = []
        self._alias_index: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        if not self.data_path.exists():
            logger.warning("Gazetteer file not found at %s", self.data_path)
            return

        with open(self.data_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        self.city = data.get("city", "Kerala")
        self.wards = {w["id"]: w for w in data.get("wards", [])}
        self.landmarks = data.get("landmarks", [])

        # Build alias index for fast fuzzy matching
        self._alias_index = []
        for lm in self.landmarks:
            entry_base = {
                "landmark_id": lm["id"],
                "name": lm["name"],
                "ward_id": lm.get("ward_id"),
                "lat": lm.get("lat"),
                "lng": lm.get("lng"),
            }
            # Add canonical name
            self._alias_index.append({**entry_base, "alias": lm["name"].lower()})
            # Add English aliases
            for alias in lm.get("aliases_en", []):
                self._alias_index.append({**entry_base, "alias": alias.lower()})
            # Add Hindi aliases
            for alias in lm.get("aliases_hi", []):
                self._alias_index.append({**entry_base, "alias": alias.lower()})

        # Also add wards as fallback matches
        for ward in data.get("wards", []):
            entry_base = {
                "landmark_id": None,
                "name": ward["name_en"],
                "ward_id": ward["id"],
                "lat": ward.get("lat", 10.50),
                "lng": ward.get("lng", 76.30),
            }
            self._alias_index.append({**entry_base, "alias": ward["name_en"].lower()})
            self._alias_index.append({**entry_base, "alias": f"ward {ward['number']}"})
            self._alias_index.append({**entry_base, "alias": ward["name_hi"].lower()})

    def _clean_query(self, query: str) -> str:
        q = query.lower()
        # Remove common prepositions and locative fillers in Hindi / Hinglish / English
        noise_words = [
            r"\bke paas\b", r"\bpaas\b", r"\bnear\b", r"\bat\b", r"\bin\b",
            r"\bopposite\b", r"\bbehind\b", r"\broof\b", r"\bchat par\b",
            r"\bfloor\b", r"\bhouse\b", r"\bgali\b", r"\bward\b"
        ]
        for nw in noise_words:
            q = re.sub(nw, " ", q, flags=re.IGNORECASE)
        q = re.sub(r"[^\w\s\u0900-\u097F]", " ", q)
        return " ".join(q.split())

    def lookup(self, text: str) -> GazetteerMatch:
        """Resolves informal place text to a landmark/ward or returns low confidence."""
        if not text or not text.strip():
            return GazetteerMatch(
                confidence=0.0,
                is_low_confidence=True
            )

        cleaned = self._clean_query(text)
        raw_lower = text.lower().strip()

        best_match = None
        highest_score = 0.0

        for entry in self._alias_index:
            alias = entry["alias"]
            # 1. Exact or substring match in cleaned or raw text
            if len(alias) >= 4 and (alias in raw_lower or alias in cleaned):
                score = 0.95
            elif cleaned and len(cleaned) >= 4 and cleaned in alias:
                score = 0.85
            else:
                # 2. Fuzzy similarity ratio
                ratio = difflib.SequenceMatcher(None, cleaned, alias).ratio()
                score = round(ratio, 3)

            longer = (
                best_match is not None
                and score == highest_score
                and score >= 0.90
                and len(alias) > len(best_match["alias"])
            )
            if score > highest_score or longer:
                highest_score = score
                best_match = entry

        if best_match and highest_score >= 0.65:
            ward_info = self.wards.get(best_match["ward_id"], {})
            lat = best_match["lat"]
            lng = best_match["lng"]
            cell = grid_cell_id(lat, lng) if lat and lng else None
            return GazetteerMatch(
                landmark_id=best_match["landmark_id"],
                landmark_name=best_match["name"],
                ward_id=best_match["ward_id"],
                ward_name=ward_info.get("name_en"),
                lat=lat,
                lng=lng,
                cell_id=cell,
                confidence=highest_score,
                matched_alias=best_match["alias"],
                is_low_confidence=False
            )

        # Low confidence match for unknown place
        return GazetteerMatch(
            confidence=round(highest_score, 2),
            is_low_confidence=True
        )

    def resolve_ward(self, place_text: Optional[str], report_text: str) -> Optional[str]:
        """Prefer a numbered ward, then the landmark named in the full report.

        The extracted place is often the clause after 'near' and drops the landmark.
        """
        blob = f"{place_text or ''} {report_text or ''}".translate(str.maketrans("०१२३४५६७८९", "0123456789"))
        numbered = re.search(r"(?:ward|वार्ड)\s*(\d+)", blob, flags=re.IGNORECASE)
        if numbered:
            candidate = f"ward_{int(numbered.group(1))}"
            if candidate in self.wards:
                return candidate
        for query in (report_text, place_text):
            if not query or not str(query).strip():
                continue
            geo = self.lookup(query)
            if geo.ward_id and not geo.is_low_confidence:
                return geo.ward_id
        return None


gazetteer = Gazetteer()
