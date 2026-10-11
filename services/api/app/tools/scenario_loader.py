import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
import yaml
from app.models.scenario import ScenarioConfig

logger = logging.getLogger("relief_desk.scenario_loader")

# Project root path resolution
PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCENARIOS_DIR = PROJECT_ROOT / "data" / "scenarios"
SAFETY_LINES_PATH = PROJECT_ROOT / "data" / "safety_lines.json"


class ScenarioRegistry:
    def __init__(self, scenarios_dir: Optional[Path] = None, safety_path: Optional[Path] = None):
        self.scenarios_dir = scenarios_dir or SCENARIOS_DIR
        self.safety_path = safety_path or SAFETY_LINES_PATH
        self._scenarios: Dict[str, ScenarioConfig] = {}
        self._safety_lines: Dict[str, Dict[str, str]] = {}
        self.reload()

    def reload(self) -> None:
        self._scenarios.clear()
        if self.scenarios_dir.exists():
            for yaml_path in self.scenarios_dir.glob("*.yaml"):
                try:
                    with open(yaml_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                    config = ScenarioConfig(**data)
                    self._scenarios[config.id] = config
                    logger.info("Loaded scenario pack '%s' from %s", config.id, yaml_path.name)
                except Exception as e:
                    logger.error("Failed to load scenario pack from %s: %s", yaml_path, e)

        if self.safety_path.exists():
            try:
                with open(self.safety_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                self._safety_lines = content.get("safety_lines", {})
            except Exception as e:
                logger.error("Failed to load safety lines from %s: %s", self.safety_path, e)

    def get_scenario(self, scenario_id: str = "flood") -> Optional[ScenarioConfig]:
        return self._scenarios.get(scenario_id)

    def list_scenarios(self) -> List[ScenarioConfig]:
        return list(self._scenarios.values())

    def get_safety_line(self, line_id: str, lang: str = "en") -> str:
        line = self._safety_lines.get(line_id)
        if not line:
            return "Call 112 in an emergency."
        return line.get(lang) or line.get("en") or "Call 112 in an emergency."


# Singleton instance
scenario_registry = ScenarioRegistry()
