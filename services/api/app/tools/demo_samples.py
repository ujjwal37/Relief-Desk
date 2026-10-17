"""Synthetic one-click samples for the judge tour. Hindi/Malayalam voice and a generated flood photo."""
from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict, Optional

HINDI_TEXT = (
    "नमस्ते, हम पुलिंकुन्नु मंदिर के पास छत पर फंसे हैं। "
    "पानी कमर तक आ गया है, घर में 4 लोग हैं, एक छोटा बच्चा और बुजुर्ग दादी हैं। कृपया जल्दी नाव भेजिए।"
)
VOICE_TEXT = (
    "नमस्ते, कावालम जेट्टी के पास मेरी दादी बीमार हैं। "
    "उनकी दवा खत्म हो गई है। घर में दो लोग हैं। कृपया मेडिकल टीम भेजिए।"
)
DUP_TEXT = (
    "Second caller: 6 people are stuck on the terrace by Pulinkunnu temple. "
    "Flood water is at the windows. We need a rescue boat. Different wording from the first report."
)
PHOTO_CAPTION = (
    "Synthetic flood photo near a Kerala house: water at window level, two people on the roof. "
    "Need a boat. This is a demo image."
)
CHALAKUDY = {"lat": 9.4549, "lng": 76.4272}  # Pulinkunnu, Kuttanad (name kept for imports)
ALUVA = {"lat": 9.4834, "lng": 76.4560}  # Kavalam, Kuttanad


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
        "voice-hi": root / "voice" / "VN-ALUVA-TTS.wav",
        "VN-ALUVA-TTS": root / "voice" / "VN-ALUVA-TTS.wav",
        "VN-HI-TTS": root / "voice" / "VN-HI-TTS.wav",
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
            "transcript": VOICE_TEXT,
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
        "duplicate": {"kind": "duplicate", "text": DUP_TEXT, "lang": "en"},
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
            "location_pin": CHALAKUDY,
        }
    if kind == "duplicate":
        return {
            "text": DUP_TEXT,
            "raw_text": DUP_TEXT,
            "channel": "text",
            "lang": "en",
            "source_id": "demo_sample_duplicate",
            "scenario_id": "flood",
            "location_pin": CHALAKUDY,
        }
    if kind == "voice":
        path = sample_path("voice-hi")
        payload: Dict[str, Any] = {
            "channel": "voice",
            "lang": "hi",
            "voice_note_id": "VN-ALUVA-TTS" if path else "VN-01",
            "source_id": "demo_sample_voice",
            "scenario_id": "flood",
            "location_pin": ALUVA,
        }
        if path:
            payload["audio_base64"] = base64.b64encode(path.read_bytes()).decode("ascii")
        return payload
    if kind == "photo":
        path = sample_path("photo-flood")
        if path is None:
            raise ValueError("Flood photo sample is missing")
        from app.tools.images import jpeg_downscale

        image = jpeg_downscale(path.read_bytes())
        return {
            "text": "",
            "raw_text": "",
            "channel": "photo",
            "lang": "en",
            "image_base64": base64.b64encode(image).decode("ascii"),
            "mime_type": "image/jpeg",
            "source_id": "demo_sample_photo",
            "scenario_id": "flood",
            "location_pin": CHALAKUDY,
        }
    raise ValueError("kind must be hindi, voice, photo, or duplicate")
