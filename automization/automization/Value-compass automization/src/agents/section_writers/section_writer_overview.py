from typing import Dict, Any, List, Optional
from .base_section_writer import BaseSectionWriter


class OverviewSectionWriter(BaseSectionWriter):
    """
    Section writer for Part 1: Overall Perspectives of LLM Value Evaluation.
    Covers 5 cross-cutting findings.
    """

    def __init__(
        self,
        ground_truth: Dict[str, Any],
        data_summary: Dict[str, Any],
        reasoning_summary: Dict[str, Any],
        new_insights: List[str] | None = None,
        analytics: Dict[str, Any] | None = None,
        global_signals: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            section_name="Overall Perspectives of LLM Value Evaluation",
            ground_truth=ground_truth,
            data_summary=data_summary,
            reasoning_summary=reasoning_summary,
            new_insights=new_insights,
            analytics=analytics,
            global_signals=global_signals,
        )

    def _section_instruction(self) -> str:
        return (
            "You are writing **Part 1** of the report.\n\n"
            "Output the section heading exactly as:\n"
            "  1. Overall Perspectives of LLM Value Evaluation\n\n"
            "Then output each finding with a visible sub-heading like:\n"
            "  Finding 1: <title>\n"
            "followed by coherent, flowing paragraph(s) — the same style as "
            "the original human report.\n\n"
            "This part contains 5 cross-cutting findings that synthesize "
            "insights across all evaluation frameworks (Schwartz, MFT, "
            "Safety Taxonomy, FULVA). Do NOT repeat framework-specific details "
            "that belong in Part 2 sections. Focus on meta-level patterns "
            "that emerge when viewing results jointly.\n"
        )
