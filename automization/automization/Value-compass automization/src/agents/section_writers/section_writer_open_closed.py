from typing import Dict, Any, List, Optional
from .base_section_writer import BaseSectionWriter


class OpenClosedSectionWriter(BaseSectionWriter):
    """
    Section writer for Proprietary vs. Open-Sourcing LLMs (Part 2).
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
            section_name="Proprietary vs. Open-Sourcing LLMs",
            ground_truth=ground_truth,
            data_summary=data_summary,
            reasoning_summary=reasoning_summary,
            new_insights=new_insights,
            analytics=analytics,
            global_signals=global_signals,
        )

    def _section_instruction(self) -> str:
        return (
            "You are writing a sub-section of **Part 2** of the report.\n\n"
            "Output the sub-section heading exactly as:\n"
            "  ◼ Proprietary vs. Open-Sourcing LLMs\n\n"
            "Then output each finding with a visible sub-heading like:\n"
            "  Finding 1: <title>\n"
            "followed by coherent, flowing paragraph(s).\n\n"
            "This section compares proprietary and open-source models on "
            "safety alignment and value expression capability.\n"
        )
