"""Freeze the original held-out ids, then add train-only labelled reports.

The first 240 messages keep their split: MSG-0001..MSG-0072 are dev,
MSG-0073..MSG-0240 are test. Nothing new is added to the test list.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "synthetic" / "flood_v1"
SPLIT = DATA / "split.json"
SEED = 42


def main() -> None:
    messages = [json.loads(line) for line in (DATA / "messages.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    labels = [json.loads(line) for line in (DATA / "labels.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    if not SPLIT.exists():
        if len(messages) < 240:
            raise SystemExit("expected the original 240 messages before freezing the test ids")
        original = messages[:240]
        payload = {
            "seed": SEED,
            "dev_ids": [row["id"] for row in original[:72]],
            "test_ids": [row["id"] for row in original[72:240]],
            "note": "Test ids are the original messages after the first 72. Later ids are train only and must not be added here.",
        }
        SPLIT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    else:
        payload = json.loads(SPLIT.read_text(encoding="utf-8"))

    have = {row["id"] for row in messages}
    if "MSG-0241" in have:
        print(f"train rows already present ({len(messages)} messages)")
        return

    gazetteer = json.loads((ROOT / "data" / "gazetteer" / "kerala_gazetteer.json").read_text(encoding="utf-8"))
    places = []
    for mark in gazetteer["landmarks"]:
        alias = (mark.get("aliases_en") or [None])[0]
        if not alias or len(alias) < 8:
            continue
        places.append(mark)
        if len(places) == 12:
            break
    if len(places) < 12:
        raise SystemExit("gazetteer did not yield 12 landmarks")

    kinds = [
        ("rescue", "stranded, send a boat", "फंसे हैं, नाव भेजो", "chhat par hain, boat bhejo"),
        ("medical", "need medicine and a doctor", "दवा और डॉक्टर चाहिए", "dawai aur doctor chahiye"),
        ("food", "need ration packets", "राशन पैकेट चाहिए", "ration packets chahiye"),
        ("shelter", "need shelter, roof collapsed", "आश्रय चाहिए, घर डूब गया", "jagah chahiye, ghar doob gaya"),
    ]
    extra_rows = []
    extra_labels = []
    n = 0

    def add(text: str, lang: str, label_type: str, ground: dict) -> None:
        nonlocal n
        n += 1
        mid = f"MSG-{240 + n:04d}"
        extra_rows.append({
            "id": mid,
            "text": text,
            "lang": lang,
            "channel": "text",
            "source_id": f"src_train_{n:03d}",
            "timestamp": "2026-10-12T12:00:00Z",
        })
        extra_labels.append({"message_id": mid, "label_type": label_type, "ground_truth": ground})

    for i, place in enumerate(places):
        name = place["aliases_en"][0]
        people = 2 + (i % 6)
        for kind, en, hi, hing in kinds:
            vuln = {"child": i % 2 == 0, "elderly": i % 3 == 0, "disabled": False, "pregnant": False, "medical_need": kind == "medical"}
            ground = {
                "type": kind,
                "ward_id": place["ward_id"],
                "landmark_id": place["id"],
                "people": people,
                "vulnerable": vuln,
                "hazard": "stranded" if kind == "rescue" else "none",
                "true_urgency": "high" if kind == "rescue" else "medium",
                "lat": place["lat"],
                "lng": place["lng"],
            }
            care_en = " Children present." if vuln["child"] else ""
            care_hi = " बच्चे भी हैं।" if vuln["child"] else ""
            care_h = " bache hain." if vuln["child"] else ""
            add(f"{people} people {en} near {name}.{care_en}", "en", "single_incident", ground)
            add(f"{name} के पास {people} लोग {hi}।{care_hi}", "hi", "single_incident", ground)
            add(f"{name} ke paas {people} log {hing}.{care_h}", "hinglish", "single_incident", ground)

    # Reworded pairs and a short update, still train-only.
    for i in range(4):
        place = places[i]
        name = place["aliases_en"][0]
        people = 3
        ground = {
            "type": "rescue",
            "ward_id": place["ward_id"],
            "landmark_id": place["id"],
            "people": people,
            "duplicate_of_incident": f"TRAIN-{place['id']}",
            "lat": place["lat"],
            "lng": place["lng"],
        }
        add(f"another report, same here, {people} people stranded near {name}, send a boat", "en", "duplicate_of", ground)
        add(f"update: now {people + 2} people stranded near {name}, boat bhejo", "hinglish", "update_of", {**ground, "people": people + 2})

    for i in range(4):
        place = places[i + 4]
        add(
            f"FREE MONEY click bit.ly win iphone send OTP near {place['aliases_en'][0]}",
            "en",
            "hoax",
            {"hoax_reason": "spam phrase", "ward_id": place["ward_id"]},
        )

    messages.extend(extra_rows)
    labels.extend(extra_labels)
    (DATA / "messages.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in messages), encoding="utf-8")
    (DATA / "labels.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in labels), encoding="utf-8")
    print(f"wrote {len(messages)} messages; test ids frozen at {len(payload['test_ids'])}")


if __name__ == "__main__":
    main()
