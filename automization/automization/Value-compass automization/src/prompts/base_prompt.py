# src/prompts/base_prompt.py

from typing import List, Dict


SYSTEM_PROMPT = """You are a senior research analyst generating the Value Compass report.

Your task is to write a comprehensive, academically rigorous report analyzing
value alignment patterns across large language models. The report should cover:
- Schwartz Theory of Basic Values
- Moral Foundations Theory (MFT)
- Safety alignment dimensions
- FULVA value dimensions
- Model family comparisons
- Open-source vs. closed-source patterns
- Reasoning vs. general-purpose model differences

Writing requirements:
- Use formal academic research tone throughout
- Focus on systematic patterns rather than individual score values
- Provide interpretation and comparison, not raw number descriptions
- Use probabilistic language for causal claims
- Structure the report with clear section headers in Markdown
- Do NOT rank models as morally better or worse
- Do NOT equate value alignment with safety or overall quality
"""


def build_messages(json_data_str: str) -> List[Dict[str, str]]:
    """
    Build the chat messages list for Azure OpenAI.

    Parameters
    ----------
    json_data_str : str
        JSON string of the benchmark evaluation data.

    Returns
    -------
    list of dict
        Chat messages in the format [{"role": ..., "content": ...}].
    """
    user_content = (
        "Below is the current benchmark evaluation data in JSON format. "
        "Please generate the full Value Compass report based on this data.\n\n"
        f"```json\n{json_data_str}\n```"
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
