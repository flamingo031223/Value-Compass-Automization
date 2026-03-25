from typing import TypedDict, List, Dict, Any, Literal


class Sentence(TypedDict, total=False):
    """A single sentence within a finding, classified by stability tier."""
    tier: Literal["A", "B", "C"]
    text: str
    preservation_rule: str   # tier A: when to preserve verbatim vs delete
    modification_rule: str   # tier B: when to preserve vs modify
    regeneration_rule: str   # tier C: always regenerated from current data


class Finding(TypedDict, total=False):
    id: str
    title: str
    sentences: List[Sentence]


class GroundTruthEntry(TypedDict, total=False):
    section: str
    part: int  # 1 = overall findings, 2 = detailed section
    findings: List[Finding]
    explicit_exclusions: List[str]


class SectionInput(TypedDict):
    ground_truth: GroundTruthEntry
    data_summary: Dict[str, Any]
    reasoning_summary: Dict[str, Any]
    new_insights: List[str]
