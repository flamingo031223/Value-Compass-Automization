import pytest
from unittest.mock import patch


@pytest.fixture
def sample_ground_truth():
    """Ground truth fixture matching the new 3-tier YAML structure."""
    return {
        "section": "Test Section",
        "part": 2,
        "findings": [
            {
                "id": "finding_1",
                "title": "Test Finding",
                "sentences": [
                    {
                        "tier": "A",
                        "text": "Models show consistent test patterns.",
                        "preservation_rule": "Preserve verbatim if pattern holds.",
                    },
                    {
                        "tier": "B",
                        "text": "This suggests underlying alignment properties.",
                        "modification_rule": "Preserve when trend unchanged.",
                    },
                    {
                        "tier": "C",
                        "text": "For example, GPT-4o scores 0.85 on dimension X.",
                        "regeneration_rule": "Regenerate from current data.",
                    },
                ],
            }
        ],
        "explicit_exclusions": [
            "Do not rank models as better or worse.",
        ],
    }


@pytest.fixture
def sample_data_summary():
    return {
        "schwartz": {"score_mean": 0.72},
        "mft": {"score_mean": 0.65},
    }


@pytest.fixture
def sample_reasoning_summary():
    return {
        "reuse_core_conclusions": True,
        "reuse_medium_insights": True,
        "dimensions_to_reconsider": [],
        "models_to_highlight": [],
    }


@pytest.fixture
def mock_llm_response():
    """Patch aoai_client.chat_completion to avoid real API calls in tests."""
    with patch("src.pipeline.aoai_client.chat_completion") as mock_chat:
        mock_chat.return_value = "## Test Section\n\nMocked LLM output for testing."
        yield mock_chat
