# src/agents/section_writers/section_writer_fulva.py

from typing import Dict, Any, List, Optional
from .base_section_writer import BaseSectionWriter


class FULVASectionWriter(BaseSectionWriter):
    """
    Section writer for LLM's Unique Value System (FULVA) (Part 2).
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
            section_name="LLM's Unique Value System",
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
            "  ◼ LLM's Unique Value System\n\n"
            "Then output each finding with a visible sub-heading like:\n"
            "  Finding 1: <title>\n"
            "followed by coherent, flowing paragraph(s).\n\n"
            "This section analyzes LLMs' unique value dimensions including "
            "user-oriented vs self-competence, social vs idealistic, and "
            "ethical vs professional value trade-offs.\n\n"
            "### Finding 1 — Ethical vs Professional dual-threshold rule (CRITICAL)\n\n"
            "The claim that 'LLMs prioritize Ethical over Professional values as a consistent "
            "trend' requires BOTH conditions to hold:\n"
            "  1. Mean gap (Ethical − Professional) > 0.05\n"
            "  2. More than 65% of individual models show Ethical > Professional\n\n"
            "Check the Writing Guidance field 'f1_weaken_ethical_professional':\n"
            "  - If TRUE: the dual threshold is NOT met. You MUST weaken or remove the "
            "'Ethical over Professional' sub-clause. Do NOT preserve it as a 'consistent trend'. "
            "The reason is provided in 'f1_weaken_reason'. Replace with hedged language such as "
            "'a slight tendency' or 'no consistent preference', as appropriate.\n"
            "  - If absent or FALSE: both thresholds pass — preserve the claim as-is.\n"
        )
