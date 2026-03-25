import yaml
from pathlib import Path
from typing import Dict, Any, List


# Mapping from YAML file names to section names (matching PDF structure)
SECTION_REGISTRY = {
    # Part 1: Overall (5 findings)
    "overall_findings": "Overall Perspectives of LLM Value Evaluation",
    # Part 2: Detailed sections (2 findings each)
    "schwartz": "Schwartz Theory of Basic Values",
    "mft": "Moral Foundation Theory",
    "safety": "Safety Taxonomy",
    "fulva": "LLM's Unique Value System",
    "open_closed": "Proprietary vs. Open-Sourcing LLMs",
    "model_families": "LLM Families",
    "reasoning": "Reasoning vs. Normal Model",
}

PART1_SECTIONS = ["overall_findings"]
PART2_SECTIONS = ["schwartz", "mft", "safety", "fulva", "open_closed", "model_families", "reasoning"]


class GroundTruthStore:
    def __init__(self, ground_truth_dir: str = "ground_truth"):
        self.ground_truth_dir = Path(ground_truth_dir)

    def load(self, section: str) -> Dict[str, Any]:
        """
        Load ground truth YAML for a given section key.
        """
        path = self.ground_truth_dir / f"{section}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Ground truth not found for section: {section}")

        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        """
        Load all ground truth YAMLs.
        Returns dict keyed by section file name.
        """
        result = {}
        for key in SECTION_REGISTRY:
            try:
                result[key] = self.load(key)
            except FileNotFoundError:
                pass
        return result

    def load_part1(self) -> List[Dict[str, Any]]:
        """Load Part 1 (overview) ground truths."""
        return [self.load(key) for key in PART1_SECTIONS]

    def load_part2(self) -> List[Dict[str, Any]]:
        """Load Part 2 (detailed sections) ground truths."""
        return [self.load(key) for key in PART2_SECTIONS]
