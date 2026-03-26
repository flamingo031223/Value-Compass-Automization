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
            "safety alignment and value expression capability.\n\n"
            "### Background Knowledge: Proprietary vs. Open-Source Models\n\n"
            "**Definitions**\n"
            "- Proprietary models (labelled 'Close' in this benchmark): models whose "
            "weights are NOT publicly released. Access is provided exclusively through "
            "commercial APIs. Examples include the GPT family (OpenAI), Claude family "
            "(Anthropic), Gemini family (Google), Grok (xAI), and Qwen/Baichuan/GLM/Moonshot "
            "(various Chinese commercial providers).\n"
            "- Open-source models (labelled 'Open' in this benchmark): models whose weights "
            "are publicly available for download, fine-tuning, and self-hosting. "
            "Examples include the LLaMA family (Meta), Mistral family, Phi family (Microsoft), "
            "DeepSeek family, and SEA-Lion variants.\n\n"
            "**Why this distinction matters for value evaluation**\n"
            "Proprietary models typically undergo more extensive and undisclosed RLHF / "
            "Constitutional AI alignment procedures before release, which may systematically "
            "shift their value profiles. Open-source models, by contrast, often expose "
            "the base pre-training value priors more directly, with alignment varying widely "
            "depending on the instruction-tuning recipe applied by the releasing organization.\n\n"
            "**Comparison methodology**\n"
            "This section compares the two groups on:\n"
            "  1. MFT alignment: group mean EVR (Empirical Violation Ratio); "
            "lower EVR = better moral alignment. "
            "Provided in Writing Guidance as 'f1_evr_by_type'.\n"
            "  2. Schwartz value expression: group mean total Schwartz score. "
            "Provided in Writing Guidance as 'f2_schwartz_by_type'.\n"
            "Use these values to determine whether the proprietary advantage is large, "
            "moderate, or has narrowed, and calibrate your language accordingly. "
            "Do NOT assume a fixed direction -- check the data first.\n"
        )
