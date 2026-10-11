import argparse
import json
import random
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SEEDS_FILE = PROJECT_ROOT / "data" / "synthetic" / "flood_v1" / "seeds.yaml"
OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "flood_v1"


def main():
    parser = argparse.ArgumentParser(description="Generate 240 synthetic messages and labels for Relief Desk benchmark.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--output-dir", type=str, default=str(OUTPUT_DIR))
    args = parser.parse_args()

    random.seed(args.seed)

    with open(SEEDS_FILE, "r", encoding="utf-8") as f:
        seeds = yaml.safe_load(f)

    incidents = seeds["incidents"]
    landmarks = {lm["id"]: lm for lm in seeds["landmarks"]}
    wards = {w["id"]: w for w in seeds["wards"]}

    messages = []
    labels = []

    msg_id_counter = 1

    def make_msg(text, lang, label_type, meta):
        nonlocal msg_id_counter
        m_id = f"MSG-{msg_id_counter:04d}"
        msg_id_counter += 1
        msg_obj = {
            "id": m_id,
            "text": text,
            "lang": lang,
            "channel": meta.get("channel", "text"),
            "source_id": meta.get("source_id", f"src_user_{random.randint(100, 999)}"),
            "timestamp": meta.get("timestamp", "2026-10-12T08:00:00Z"),
        }
        lbl_obj = {
            "message_id": m_id,
            "label_type": label_type,
            "ground_truth": meta,
        }
        messages.append(msg_obj)
        labels.append(lbl_obj)

    # 1. Single Unique Incident Messages (~100)
    for i in range(100):
        inc = incidents[i % len(incidents)]
        lm = landmarks.get(inc["landmark_id"], {})
        w = wards.get(inc["ward_id"], {})
        lang = random.choices(["hi", "hinglish", "en"], weights=[0.25, 0.45, 0.30])[0]

        ppl = inc["people"]
        has_child = inc["vulnerable"].get("child", False)
        has_elderly = inc["vulnerable"].get("elderly", False)

        lm_name_en = lm.get("name", "Kerala Area")
        lm_alias_hi = lm.get("aliases_hi", [lm_name_en])[0]
        lm_alias_en = lm.get("aliases_en", [lm_name_en])[0]

        itype = inc["type"]
        if itype == "medical":
            if lang == "hi":
                text = f"{lm_alias_hi} के पास {ppl} मरीजों को दवाइयों और डॉक्टर की सख्त ज़रूरत है। "
            elif lang == "hinglish":
                text = f"{lm_alias_en} ke paas {ppl} log bimar hain oxygen aur dawa urgently chahiye. "
            else:
                text = f"{ppl} people need urgent medical supplies and medicine near {lm_alias_en}. "
        elif itype == "food":
            if lang == "hi":
                text = f"{lm_alias_hi} पर {ppl} लोगों के लिए राशन और पीने का पानी खत्म हो गया है। "
            elif lang == "hinglish":
                text = f"{lm_alias_en} me {ppl} log bhookhe hain ration aur drinking water packets bhejo. "
            else:
                text = f"{ppl} people stranded without food packets and water near {lm_alias_en}. "
        elif itype == "shelter":
            if lang == "hi":
                text = f"{lm_alias_hi} के {ppl} लोगों का घर डूब गया है, राहत शिविर में जगह चाहिए। "
            elif lang == "hinglish":
                text = f"{lm_alias_en} paas {ppl} log beghar hain temporary shelter aur tarpaulin chahiye. "
            else:
                text = f"{ppl} people need emergency shelter near {lm_alias_en}, ground floor submerged. "
        elif itype == "animal_attack":
            if lang == "hi":
                text = f"{lm_alias_hi} के पास {ppl} लोगों को आवारा कुत्तों ने काट लिया है, एंटी-रेबीज इंजेक्शन चाहिए। "
            elif lang == "hinglish":
                text = f"{lm_alias_en} ke paas aggressive dogs ne {ppl} logo ko bite kiya hai hospital le jao. "
            else:
                text = f"Aggressive pack of dogs attacked {ppl} people near {lm_alias_en}, rabies vaccine needed. "
        elif itype == "info":
            if lang == "hi":
                text = f"{lm_alias_hi} के पास पानी 3 फीट भर गया है, रास्ता बंद है।"
            elif lang == "hinglish":
                text = f"{lm_alias_en} road is blocked with 3 feet waterlogging, traffic stopped."
            else:
                text = f"Water level 3 feet and road blocked near {lm_alias_en}."
        else:
            if lang == "hi":
                text = f"{lm_alias_hi} के पास {ppl} लोग फंसे हैं, पानी बढ़ रहा है। "
            elif lang == "hinglish":
                text = f"{lm_alias_en} ke paas {ppl} log chat par hain pani bohot tezi se badh raha hai jaldi boat bhejo. "
            else:
                text = f"{ppl} people stranded near {lm_alias_en}, water rising rapidly, rescue boat needed. "

        if has_child:
            text += "बच्चे भी साथ हैं। " if lang == "hi" else ("chote bache hain. " if lang == "hinglish" else "Children present. ")
        if has_elderly:
            text += "बुजुर्गों को सहायता चाहिए।" if lang == "hi" else ("buzurg log hain. " if lang == "hinglish" else "Elderly need assistance.")

        make_msg(text, lang, "single_incident", {
            "incident_id": inc["id"],
            "type": inc["type"],
            "ward_id": inc["ward_id"],
            "landmark_id": inc["landmark_id"],
            "people": ppl,
            "vulnerable": inc["vulnerable"],
            "hazard": "water_rising",
            "true_urgency": inc.get("urgency_band", "high"),
        })

    # 2. True Duplicates (~45)
    for i in range(45):
        inc = incidents[i % len(incidents)]
        lm = landmarks.get(inc["landmark_id"], {})
        lang = random.choices(["hi", "hinglish", "en"], weights=[0.25, 0.45, 0.30])[0]
        lm_name = lm.get("name", "the area")

        if lang == "hi":
            text = f"{lm_name} में पानी भर गया है, तुरंत बचाव दल भेजो!"
        elif lang == "hinglish":
            text = f"same here near {lm_name}, pani bohot zyada hai log phase hue hain"
        else:
            text = f"Another report from {lm_name}: roads completely submerged, people on second floor needing help."

        make_msg(text, lang, "duplicate_of", {
            "duplicate_of_incident": inc["id"],
            "incident_id": inc["id"],
            "type": inc["type"],
            "ward_id": inc["ward_id"],
            "landmark_id": inc["landmark_id"],
        })

    # 3. Updates (~25)
    for i in range(25):
        inc = incidents[i % len(incidents)]
        lm = landmarks.get(inc["landmark_id"], {})
        new_count = inc["people"] + random.randint(2, 5)
        lang = random.choices(["hi", "hinglish", "en"], weights=[0.25, 0.45, 0.30])[0]

        if lang == "hi":
            text = f"अब {new_count} लोग हो गए हैं {lm.get('name', '')} पर, पानी पहली मंजिल तक आ गया है।"
        elif lang == "hinglish":
            text = f"ab {new_count} log hain paani aur badh gaya hai please hurry"
        else:
            text = f"Update for our earlier call: count is now {new_count} people, water reached 1st floor."

        make_msg(text, lang, "update_of", {
            "update_of_incident": inc["id"],
            "incident_id": inc["id"],
            "changed_fields": {"people": {"from": inc["people"], "to": new_count}},
            "people": new_count,
            "hazard": "water_rising",
        })

    # 4. Near-Miss Non-Duplicates (~25 hard negatives: same ward, different house)
    for i in range(25):
        inc = incidents[i % len(incidents)]
        w = wards.get(inc["ward_id"], {})
        lang = random.choices(["hi", "hinglish", "en"], weights=[0.25, 0.45, 0.30])[0]
        house_no = random.randint(10, 95)

        if lang == "hi":
            text = f"वार्ड {w.get('number', 1)} में मकान नंबर {house_no} में खाना खत्म हो गया है, 3 लोग हैं।"
        elif lang == "hinglish":
            text = f"ward {w.get('number', 1)} gali 3 house {house_no} alag ghar hai, yahan khana chahiye rescue nahi"
        else:
            text = f"Different house in Ward {w.get('number', 1)}, House #{house_no}: need drinking water for 2 adults."

        make_msg(text, lang, "not_duplicate", {
            "near_miss_incident": inc["id"],
            "ward_id": inc["ward_id"],
            "type": "food",
            "people": 3,
        })

    # 5. Hoax / Spam (~20)
    hoax_templates = [
        "NASA alert! Kerala dam broken, share this message to 15 groups immediately to activate army!",
        "100% verified news: call 9876543210 for free government helicopter rescue anywhere in Kerala!",
        "Special disaster relief lottery: send 500 rupees to receive emergency relief kit.",
        "Breaking: crocodile spotted on main road forward fast to warn everybody!",
    ]
    for i in range(20):
        t = random.choice(hoax_templates)
        make_msg(t, "en", "hoax", {"hoax_reason": "viral forwarded disinformation"})

    # 6. Conflicting Reports (~10)
    for i in range(10):
        inc = incidents[i % len(incidents)]
        lm = landmarks.get(inc["landmark_id"], {})
        text = f"{lm.get('name', 'Area')} road is completely dry and safe, water has drained out completely."
        make_msg(text, "en", "conflict_group", {
            "conflicts_with_incident": inc["id"],
            "claimed_hazard": "none",
        })

    # 7. Stale Reports (~10)
    for i in range(10):
        inc = incidents[i % len(incidents)]
        lm = landmarks.get(inc["landmark_id"], {})
        text = f"Old status from yesterday: 4 people waited at {lm.get('name', '')}."
        make_msg(text, "en", "stale", {
            "stale_incident": inc["id"],
            "timestamp": "2026-10-10T02:00:00Z"
        })

    # 8. Unclear / Missing Place (~5)
    unclear_templates = [
        "madad chahiye bohot paani hai",
        "please send boat immediately someone is in danger",
        "chat par hain sab log",
        "पानी बढ़ रहा है तुरंत आओ",
        "emergency help needed here",
    ]
    for i in range(5):
        t = unclear_templates[i % len(unclear_templates)]
        make_msg(t, "hinglish", "place_unknown", {"place_unknown": True})

    # Write files
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    msgs_path = out_dir / "messages.jsonl"
    lbls_path = out_dir / "labels.jsonl"

    with open(msgs_path, "w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")

    with open(lbls_path, "w", encoding="utf-8") as f:
        for l in labels:
            f.write(json.dumps(l, ensure_ascii=False) + "\n")

    print(f"Generated {len(messages)} messages -> {msgs_path}")
    print(f"Generated {len(labels)} labels -> {lbls_path}")


if __name__ == "__main__":
    main()
