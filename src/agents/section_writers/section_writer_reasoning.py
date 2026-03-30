from typing import Dict, Any, List, Optional
from .base_section_writer import BaseSectionWriter


class ReasoningSectionWriter(BaseSectionWriter):
    """
    Section writer for Reasoning vs. Normal Model (Part 2).
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
            section_name="Reasoning vs. Normal Model",
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
            "  ◼ Reasoning vs. Normal Model\n\n"
            "Then output each finding with a visible sub-heading like:\n"
            "  Finding 1: <title>\n"
            "followed by coherent, flowing paragraph(s).\n\n"
            "This section compares reasoning-enhanced LLMs with standard "
            "models on safety performance and value expression.\n\n"
            "### Background Knowledge: Reasoning Models vs. Standard Models\n\n"
            "**Definition**\n"
            "Reasoning-enhanced models (also called 'reasoning models') are LLMs that employ "
            "an extended internal deliberation process before producing a final answer. "
            "This typically involves chain-of-thought (CoT) reasoning, self-reflection, or "
            "multi-step planning carried out within the model's inference pass. The key "
            "distinction from standard models is that reasoning models allocate additional "
            "compute at inference time to think through a problem before committing to a "
            "response, rather than generating answers in a single forward pass.\n\n"
            "**Models classified as reasoning-enhanced in this benchmark**\n"
            "The following model families are treated as reasoning models in this evaluation: "
            "OpenAI o1 series (o1, o1-mini, o1-preview), OpenAI o3 series (o3, o3-mini), "
            "and DeepSeek-R1 series (DeepSeek-R1 and its variants). "
            "All other models are classified as standard (normal) models.\n\n"
            "**Why this distinction matters for value evaluation**\n"
            "The extended deliberation process may cause reasoning models to behave "
            "differently from standard models on value-sensitive prompts:\n"
            "- They may engage more carefully with moral dilemmas, potentially scoring "
            "  differently on MFT dimensions (especially Care and Fairness).\n"
            "- Their extended thinking may amplify or suppress certain Schwartz dimensions "
            "  (e.g., stronger Security or Universalism orientation).\n"
            "- On safety benchmarks, their step-by-step reasoning may help them better "
            "  identify and refuse harmful requests -- or, conversely, reason their way "
            "  into fulfilling them.\n\n"
            "**Comparison methodology**\n"
            "This section compares the two groups (reasoning vs. standard) on:\n"
            "  1. MFT alignment: group mean EVR (Empirical Violation Ratio); "
            "lower EVR = better moral alignment.\n"
            "  2. Schwartz value expression: group mean total Schwartz score.\n"
            "Use the data in the Writing Guidance block below "
            "('f1_mft_comparison', 'f2_schwartz_comparison') to determine whether "
            "reasoning models outperform, match, or underperform standard models, "
            "and adjust the finding language accordingly.\n"
        )
