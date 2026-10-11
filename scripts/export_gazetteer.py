"""
Export standalone gazetteer JSON from seeds.yaml for tools/gazetteer.py (T-011).
"""
import json
import yaml
from pathlib import Path

def export_gazetteer():
    seeds_path = Path("data/synthetic/flood_v1/seeds.yaml")
    with open(seeds_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    gazetteer_dir = Path("data/gazetteer")
    gazetteer_dir.mkdir(parents=True, exist_ok=True)
    out_file = gazetteer_dir / "kerala_gazetteer.json"

    export_data = {
        "city": data["city"]["name"],
        "label": data["city"].get("label", "Synthetic scenario inspired by Kerala floods"),
        "bbox": data["city"]["bbox"],
        "wards": data["wards"],
        "landmarks": data["landmarks"]
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(export_data, f, ensure_ascii=False, indent=2)

    print(f"Exported gazetteer to {out_file} with {len(data['landmarks'])} landmarks.")

if __name__ == "__main__":
    export_gazetteer()
