import pytest
from src.agents.section_writers.section_writer_schwartz import SchwartzSectionWriter
from src.agents.section_writers.section_writer_mft import MFTSectionWriter
from src.agents.section_writers.section_writer_safety import SafetySectionWriter
from src.agents.section_writers.section_writer_fulva import FULVASectionWriter
from src.agents.section_writers.section_writer_overview import OverviewSectionWriter
from src.agents.section_writers.section_writer_model_families import ModelFamiliesSectionWriter
from src.agents.section_writers.section_writer_open_closed import OpenClosedSectionWriter
from src.agents.section_writers.section_writer_reasoning import ReasoningSectionWriter


WRITER_CLASSES = [
    SchwartzSectionWriter,
    MFTSectionWriter,
    SafetySectionWriter,
    FULVASectionWriter,
    OverviewSectionWriter,
    ModelFamiliesSectionWriter,
    OpenClosedSectionWriter,
    ReasoningSectionWriter,
]


class TestSectionWriterInstantiation:
    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_instantiation(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name
        assert writer.ground_truth == sample_ground_truth

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_build_prompt_returns_string(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_includes_reference_findings(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Reference Findings" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_uses_internal_stability_tags(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        """Tier logic is preserved internally as STABLE/ADAPT/REFRESH tags."""
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "[STABLE]" in prompt
        assert "[ADAPT]" in prompt
        assert "[REFRESH]" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_does_not_expose_tier_abc(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        """Tier A/B/C labels must NOT appear in the prompt sent to the LLM."""
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "[Tier A]" not in prompt
        assert "[Tier B]" not in prompt
        assert "[Tier C]" not in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_includes_internal_rules(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Preserve verbatim" in prompt
        assert "Regenerate from current data" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_includes_writing_constraints(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Writing Constraints" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_requires_paragraph_style(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "paragraph" in prompt.lower()

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_forbids_numerical_scores(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Do NOT cite specific numerical scores" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_requests_new_findings_with_asterisk(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "asterisk (*)" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_includes_finding_number_and_title(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Finding 1: Test Finding" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_instructs_finding_subheadings(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        """Prompt must instruct the LLM to keep 'Finding N:' as visible sub-headings."""
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Finding" in prompt
        assert "sub-heading" in prompt.lower()

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_prompt_includes_exclusions(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Exclusions" in prompt
        assert "Do not rank models" in prompt

    @pytest.mark.parametrize("writer_cls", WRITER_CLASSES)
    def test_write_with_mocked_llm(self, writer_cls, sample_ground_truth, sample_data_summary, sample_reasoning_summary, mock_llm_response):
        writer = writer_cls(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        result = writer.write()
        assert isinstance(result, str)
        assert "Mocked LLM output" in result
        mock_llm_response.assert_called_once()


class TestSectionWriterEdgeCases:
    def test_empty_ground_truth(self, sample_data_summary, sample_reasoning_summary):
        writer = SchwartzSectionWriter(
            ground_truth={},
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Reference Findings" not in prompt

    def test_ground_truth_no_findings(self, sample_data_summary, sample_reasoning_summary):
        writer = SchwartzSectionWriter(
            ground_truth={"section": "Test", "findings": []},
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Reference Findings" not in prompt

    def test_empty_data_summary(self, sample_ground_truth, sample_reasoning_summary):
        writer = SchwartzSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary={},
            reasoning_summary=sample_reasoning_summary,
        )
        prompt = writer.build_prompt()
        assert "Data Change Summary" not in prompt

    def test_new_insights_included(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        insights = ["New pattern in model X", "Emerging trend in dimension Y"]
        writer = SchwartzSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
            new_insights=insights,
        )
        prompt = writer.build_prompt()
        assert "Candidate New Insights" in prompt
        assert "New pattern in model X" in prompt

    def test_postprocess_strips_whitespace(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = SchwartzSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.postprocess("  hello  ") == "hello"


class TestSectionNameMapping:
    """Verify each writer has the correct section name matching the PDF structure."""

    def test_overview_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = OverviewSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Overall Perspectives of LLM Value Evaluation"

    def test_schwartz_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = SchwartzSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Schwartz Theory of Basic Values"

    def test_mft_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = MFTSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Moral Foundation Theory"

    def test_safety_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = SafetySectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Safety Taxonomy"

    def test_fulva_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = FULVASectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "LLM's Unique Value System"

    def test_open_closed_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = OpenClosedSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Proprietary vs. Open-Sourcing LLMs"

    def test_model_families_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = ModelFamiliesSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "LLM Families"

    def test_reasoning_section_name(self, sample_ground_truth, sample_data_summary, sample_reasoning_summary):
        writer = ReasoningSectionWriter(
            ground_truth=sample_ground_truth,
            data_summary=sample_data_summary,
            reasoning_summary=sample_reasoning_summary,
        )
        assert writer.section_name == "Reasoning vs. Normal Model"
