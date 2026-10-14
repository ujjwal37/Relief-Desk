"""The README may only repeat numbers this repo has measured."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_readme_reports_the_frozen_split_and_does_not_invent_gemini_accuracy():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "67.3%" in text
    assert "100.0%" in text
    assert "no_api_key" in text
    assert "not measured" in text
    assert "90%" in text
    assert "under the 90%" in text or "at 67.3%" in text
    lowered = text.lower()
    assert "gemini live voice is not built" in lowered
    assert "pubsub" not in lowered or "not built" in lowered
    assert "bigquery" not in lowered or "not built" in lowered


def test_deploy_doc_does_not_claim_a_live_service():
    text = (ROOT / "deploy" / "cloudrun.md").read_text(encoding="utf-8")
    assert "no live Cloud Run URL" in text
    assert "in process memory" in text
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "PORT" in dockerfile
    assert "services/api" in dockerfile
