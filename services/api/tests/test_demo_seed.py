from app.tools.demo_seed import build_demo_reports, demo_summary, load_demo_pack
from app.tools.storage import StorageService


def test_flood_demo_pack_has_duplicates_update_hoax_and_silent_zone():
    reports = build_demo_reports()
    summary = demo_summary(reports)
    assert summary["report_count"] >= 45
    assert summary["kinds"]["duplicate"] >= 1
    assert summary["kinds"]["update"] >= 1
    assert summary["kinds"]["hoax"] >= 1
    assert summary["silent_wards"] == ["ward_12"]
    assert "ward_12" not in summary["wards_with_reports"]
    hoax = next(row for row in reports if row["kind"] == "hoax")
    assert "hoax" in hoax["flags"]
    assert "forward this to 10 groups" in hoax["text"].lower()
    update = next(row for row in reports if row["kind"] == "update")
    assert "ab 5 log hain" in update["text"]


def test_load_demo_pack_keeps_the_hoax_report():
    storage = StorageService()
    summary = load_demo_pack(storage)
    assert summary["report_count"] >= 45
    stored = storage.get_report("DR-H01")
    assert stored is not None
    assert "hoax" in stored.flags
    assert storage.get_report("DR-U01") is not None
    assert len(storage.list_reports()) >= 45
