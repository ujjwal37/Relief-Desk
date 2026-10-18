import base64
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger("relief_desk.asr")
def _find_voice_notes_file() -> Path:
    current = Path(__file__).resolve().parent
    for p in [current, *current.parents]:
        target = p / "data" / "synthetic" / "voice" / "notes.json"
        if target.exists():
            return target
    return Path(__file__).resolve().parents[3] / "data" / "synthetic" / "voice" / "notes.json"

VOICE_NOTES_FILE = _find_voice_notes_file()


class ASRResult(BaseModel):
    transcript: str
    asr_confidence: float
    detected_language: str
    voice_note_id: Optional[str] = None
    duration_sec: float = 5.0
    synthetic: bool = True


class VoiceNoteMetadata(BaseModel):
    id: str
    name: str
    lang: str
    duration_sec: int
    transcript: str
    asr_confidence: float


class ASRService:
    def __init__(self):
        self._notes_cache: Dict[str, Dict[str, Any]] = {}
        self._load_notes()

    def _load_notes(self):
        if VOICE_NOTES_FILE.exists():
            try:
                with open(VOICE_NOTES_FILE, "r", encoding="utf-8") as f:
                    notes = json.load(f)
                    for n in notes:
                        self._notes_cache[n["id"]] = n
                logger.info("Loaded %d synthetic voice notes for ASR pipeline", len(self._notes_cache))
            except Exception as e:
                logger.error("Failed to load synthetic voice notes: %s", e)

    def list_voice_notes(self) -> List[VoiceNoteMetadata]:
        """Returns catalog of pre-recorded synthetic voice notes for live demo."""
        return [
            VoiceNoteMetadata(
                id=n["id"],
                name=n["name"],
                lang=n["lang"],
                duration_sec=n["duration_sec"],
                transcript=n["transcript"],
                asr_confidence=n["asr_confidence"],
            )
            for n in self._notes_cache.values()
        ]

    def transcribe(
        self,
        voice_note_id: Optional[str] = None,
        audio_base64: Optional[str] = None,
        audio_bytes: Optional[bytes] = None,
        lang_hint: str = "hi",
    ) -> ASRResult:
        """Transcribes a synthetic voice note in English or Hindi."""
        # Live audio (including demo TTS) must go through Gemini. Catalog notes are the fallback.
        if audio_base64:
            try:
                audio_bytes = base64.b64decode(audio_base64)
            except Exception:
                pass

        # Catalog id without attached audio is the recorded-note path (VN-01 etc.).
        if voice_note_id and voice_note_id in self._notes_cache and not audio_bytes:
            note = self._notes_cache[voice_note_id]
            logger.info("ASR matched pre-recorded synthetic note %s", voice_note_id)
            return ASRResult(
                transcript=note["transcript"],
                asr_confidence=note["asr_confidence"],
                detected_language=note["lang"],
                voice_note_id=voice_note_id,
                duration_sec=float(note.get("duration_sec", 5)),
            )

        # Live multimodal ASR when Gemini (Vertex AI or Studio) is on and we have audio bytes.
        from app.llm.client import (
            build_genai_client,
            resolve_model,
            gemini_live,
            _is_vertex_fallback_error,
            _log_vertex_warning,
        )

        if gemini_live() and audio_bytes:
            try:
                from google.genai import types

                client, provider = build_genai_client(timeout_s=20.0)
                model_name = resolve_model(strong=False, provider=provider)
                prompt = f"""You are a crisis dispatch speech-to-text transcriber.
Transcribe this emergency voice recording verbatim.
Supported languages: English and Hindi (Devanagari script).
Return ONLY the raw transcription without any commentary or quotation marks."""

                try:
                    response = client.models.generate_content(
                        model=model_name,
                        contents=[
                            types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                            prompt,
                        ],
                        config=types.GenerateContentConfig(temperature=0.0),
                    )
                except Exception as exc:
                    if provider == "vertex" and _is_vertex_fallback_error(exc):
                        _log_vertex_warning(
                            f"Vertex ASR call failed with auth/perm error ({exc}); falling back to AI Studio"
                        )
                        fallback_client, fallback_prov = build_genai_client(timeout_s=20.0, force_studio=True)
                        response = fallback_client.models.generate_content(
                            model=resolve_model(strong=False, provider=fallback_prov),
                            contents=[
                                types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav"),
                                prompt,
                            ],
                            config=types.GenerateContentConfig(temperature=0.0),
                        )
                    else:
                        raise

                if response.text and response.text.strip():
                    return ASRResult(
                        transcript=response.text.strip(),
                        asr_confidence=0.92,
                        detected_language=lang_hint,
                        duration_sec=6.0,
                    )
            except Exception as e:
                logger.warning("Gemini live audio transcription fallback: %s", e)

        # Catalog fallback when live ASR is off, including the Aluva demo note.
        if voice_note_id and voice_note_id in self._notes_cache:
            note = self._notes_cache[voice_note_id]
            return ASRResult(
                transcript=note["transcript"],
                asr_confidence=note["asr_confidence"],
                detected_language=note["lang"],
                voice_note_id=voice_note_id,
                duration_sec=float(note.get("duration_sec", 5)),
            )
        fallback_note = self._notes_cache.get("VN-01")
        if fallback_note:
            return ASRResult(
                transcript=fallback_note["transcript"],
                asr_confidence=fallback_note["asr_confidence"],
                detected_language=fallback_note["lang"],
                voice_note_id="VN-01",
                duration_sec=7.0,
            )

        # Default minimal fallback
        return ASRResult(
            transcript="नमस्ते, वार्ड 7 में शिव मंदिर के पास पानी भर गया है, तुरंत नाव भेजिए।",
            asr_confidence=0.90,
            detected_language="hi",
            duration_sec=5.0,
        )


asr_service = ASRService()
