"""Source files must not contain the U+00E2 mojibake marker from a bad UTF-8 read."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SKIP = {".git", "node_modules", "dist", ".angular", "coverage", ".venv"}
EXTS = {".scss", ".css", ".html", ".ts", ".json", ".py", ".svg", ".yaml", ".yml", ".mjs", ".md", ".js"}
LANDING = ROOT / "apps" / "web" / "src" / "app" / "landing" / "landing.component.scss"


def test_landing_checkmark_uses_a_css_escape():
    text = LANDING.read_text(encoding="utf-8")
    assert "content:'\\2713 '" in text


def test_repo_has_no_mojibake_a_circumflex():
    needle = "\u00e2"
    hits = []
    for path in ROOT.rglob("*"):
        if any(part in SKIP for part in path.parts) or path.suffix.lower() not in EXTS or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if needle not in text:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if needle in line:
                hits.append(f"{path.relative_to(ROOT)}:{number}")
    assert hits == []
