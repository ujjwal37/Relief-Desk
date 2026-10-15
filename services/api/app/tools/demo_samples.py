"""Synthetic one-click samples for the judge tour. Hindi/Malayalam voice and a generated flood photo."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

HINDI_TEXT = (
    "नमस्ते, हम वार्ड 7 में चालाकुडी महादेव मंदिर के पास छत पर फंसे हैं। "
    "पानी कमर तक आ गया है, घर में 4 लोग हैं, एक छोटा बच्चा और बुजुर्ग दादी हैं। कृपया जल्दी नाव भेजिए।"
)
PHOTO_CAPTION = (
    "Synthetic flood photo near a Kerala house: water at window level, two people on the roof. "
    "Need a boat. This is a demo image."
)


def _data_root() -> Path:
    current = Path(__file__).resolve().parent
    for parent in [current, *current.parents]:
        voice = parent / "data" / "synthetic" / "voice"
        if voice.exists():
            return parent / "data" / "synthetic"
    return Path(__file__).resolve().parents[4] / "data" / "synthetic"


def sample_path(sample_id: str) -> Optional[Path]:
    root = _data_root()
    mapping = {
        "voice-hi": root / "voice" / "VN-HI-TTS.wav",
        "VN-01": root / "voice" / "VN-01.wav",
        "photo-flood": root / "samples" / "flood_roof.jpg",
    }
    path = mapping.get(sample_id)
    if path and path.exists():
        return path
    return None


def catalog() -> Dict[str, Any]:
    voice = sample_path("voice-hi") or sample_path("VN-01")
    photo = sample_path("photo-flood")
    return {
        "hindi_text": {"kind": "hindi", "text": HINDI_TEXT, "lang": "hi"},
        "voice": {
            "kind": "voice",
            "id": "voice-hi" if sample_path("voice-hi") else "VN-01",
            "lang": "hi",
            "transcript": HINDI_TEXT,
            "url": "/api/demo/samples/voice-hi" if sample_path("voice-hi") else "/api/demo/samples/VN-01",
            "bytes": voice.stat().st_size if voice else 0,
        },
        "photo": {
            "kind": "photo",
            "id": "photo-flood",
            "caption": PHOTO_CAPTION,
            "url": "/api/demo/samples/photo-flood" if photo else None,
            "bytes": photo.stat().st_size if photo else 0,
        },
    }


def sample_payload(kind: str) -> Dict[str, Any]:
    kind = (kind or "hindi").lower()
    if kind == "hindi":
        return {
            "text": HINDI_TEXT,
            "raw_text": HINDI_TEXT,
            "channel": "text",
            "lang": "hi",
            "source_id": "demo_sample_hindi",
            "scenario_id": "flood",
        }
    if kind == "voice":
        path = sample_path("voice-hi")
        payload: Dict[str, Any] = {
            "text": HINDI_TEXT,
            "raw_text": HINDI_TEXT,
            "channel": "voice",
            "lang": "hi",
            "voice_note_id": "VN-HI-TTS" if path else "VN-01",
            "source_id": "demo_sample_voice",
            "scenario_id": "flood",
        }
        if path:
            payload["audio_base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
        return payload
    if kind == "photo":
        path = sample_path("photo-flood")
        if path is None:
            raise ValueError("Flood photo sample is missing")
        return {
            "text": PHOTO_CAPTION,
            "raw_text": PHOTO_CAPTION,
            "channel": "photo",
            "lang": "en",
            "image_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
            "mime_type": "image/jpeg",
            "source_id": "demo_sample_photo",
            "scenario_id": "flood",
        }
    raise ValueError("kind must be hindi, voice, or photo")
