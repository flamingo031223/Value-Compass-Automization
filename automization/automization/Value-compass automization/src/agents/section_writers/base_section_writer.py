# src/agents/section_writers/base_section_writer.py

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseSectionWriter(ABC):
    """
    Base class for all section writers.
    Each section writer generates ONE report section based on:
      - ground truth knowledge (with internal A/B/C tier logic)
      - detected data changes
      - reasoning outcomes
      - optional new insights
      - optional global signals (hierarchy reversals, new models, intensity metrics)

    Do NOT use any Unicode symbols that may break LaTeX, including: ◼ ■ ◆ ▮ ▯ ▰ ▱ ▪ ▫ ● • ★ ☆ ✓ ✔ ✗ ✘ and similar.
Use plain ASCII text only.

    """

    def __init__(
        self,
        section_name: str,
        ground_truth: Dict[str, Any],
        data_summary: Dict[str, Any],
        reasoning_summary: Dict[str, Any],
        new_insights: Optional[List[str]] = None,
        analytics: Optional[Dict[str, Any]] = None,
        global_signals: Optional[Dict[str, Any]] = None,
    ):
        self.section_name = section_name
        self.ground_truth = ground_truth
        self.data_summary = data_summary
        self.reasoning_summary = reasoning_summary
        self.new_insights = new_insights or []
        self.analytics = analytics or {}
        self.global_signals = global_signals or {}

    # ---------- Main public entry ----------

    def write(self) -> str:
        """
        Main entry for section generation.
        Returns markdown text for this section.
        """
        prompt = self.build_prompt()
        section_text = self.call_llm(prompt)
        return self.postprocess(section_text)

    # ---------- Prompt construction ----------

    def build_prompt(self) -> str:
        """
        Assemble the full prompt used to generate this section.
        """
        parts = [
            self._section_instruction(),
            self._global_signals_block(),
            self._replacement_instructions_block(),
            self._ground_truth_block(),
            self._data_change_block(),
            self._reasoning_block(),
            self._new_insight_block(),
            self._writing_constraints(),
        ]
        return "\n\n".join([p for p in parts if p.strip()])

    @abstractmethod
    def _section_instruction(self) -> str:
        """
        High-level instruction of what this section is about.
        Must be implemented by each concrete section writer.
        """
        pass

    def _global_signals_block(self) -> str:
        """
        Render critical global signals that override local section decisions.
        These signals broadcast system-wide changes (reversals, new models) to
        ALL section writers so that no section silently contradicts another.
        """
        if not self.global_signals:
            return ""

        gs = self.global_signals
        lines: List[str] = []

        # --- Major reversals ---
        if gs.get("schwartz_hierarchy_reversed"):
            lines.append(
                "CRITICAL GLOBAL SIGNAL: The Schwartz value hierarchy has REVERSED. "
                "The prior ordering (Universalism/Benevolence at top) no longer holds. "
                "ANY claim in this section that relies on that ordering MUST be rewritten "
                "or deleted and replaced with a *NEW* insight reflecting the new hierarchy."
            )

        if gs.get("fulva_user_orientation_reversed"):
            lines.append(
                "CRITICAL GLOBAL SIGNAL: The FULVA user-orientation bias has REVERSED. "
                "Claims that 'LLMs score higher on user-oriented vs. self-competence dimensions' "
                "are NO LONGER VALID. Rewrite or delete such claims."
            )

        if gs.get("safety_ceiling_weakened"):
            lines.append(
                "GLOBAL SIGNAL: The safety ceiling effect is weakening. "
                "Statements about 'near-perfect safety scores across all models' should be "
                "softened or updated."
            )

        if gs.get("reasoning_models_now_outperform"):
            lines.append(
                "GLOBAL SIGNAL: Reasoning models NOW outperform normal models on MFT — "
                "this is a reversal. Any sentence claiming reasoning models show 'only marginal "
                "gains' should be revised."
            )

        if not gs.get("ov3_cross_example_still_valid", True):
            lines.append(
                "GLOBAL SIGNAL: The cross-framework example for o3-mini (low Fairness + "
                "high Rep_Toxicity) is NO LONGER VALID. Do NOT use this as a correlation "
                "example. Find an alternative model that still demonstrates cross-framework "
                "consistency from the current data."
            )

        # --- New models ---
        new_models = gs.get("newly_added_models", [])
        if new_models:
            lines.append(
                f"NEW MODELS DETECTED: The following models appear in the new data but "
                f"were not in the baseline: {', '.join(new_models)}. "
                f"When replacing example models or listing top performers, CONSIDER these "
                f"new models if they rank highly. Do NOT silently ignore them."
            )

        # --- Intensity language guidance ---
        intensity = gs.get("intensity_metrics", {})
        if intensity:
            intensity_lines = []
            prop_intensity = intensity.get("prop_vs_open_intensity")
            if prop_intensity:
                intensity_lines.append(
                    f"proprietary vs. open-source MFT advantage: use '{prop_intensity}' "
                    f"(gap={intensity.get('prop_vs_open_mft_gap', '?')} pp)"
                )
            reasoning_intensity = intensity.get("reasoning_mft_intensity")
            if reasoning_intensity:
                intensity_lines.append(
                    f"reasoning vs. normal MFT improvement: use '{reasoning_intensity}' "
                    f"(advantage={intensity.get('reasoning_mft_advantage', '?')} pp)"
                )
            if intensity_lines:
                lines.append(
                    "INTENSITY LANGUAGE CALIBRATION (use these exact words to match data):\n  "
                    + "\n  ".join(intensity_lines)
                )

        if not lines:
            return ""

        header = "### Global Pipeline Signals (override local section defaults)"
        return header + "\n\n" + "\n\n".join(lines)

    def _replacement_instructions_block(self) -> str:
        """
        Renders:
          1. Explicit old->new model name replacement instructions (from verifier)
          2. Banned model names (phantom models not in new dataset)
          3. Suppressed phrases (L1 sentences invalidated by trend reversal — Bug #4)
          4. Mandatory notes from reasoning guide (Bug #1 open-source validation,
             Bug #2 Schwartz F2 authoritative top-3, Bug #3 MFT/Safety disambiguation)
        """
        rs = self.reasoning_summary
        if not isinstance(rs, dict):
            return ""

        replace_lines: list = []
        banned: list = []
        suppressed: list = []
        mandatory_notes: list = []
        finding_labels = {
            "f1_status": "Finding 1",
            "f2_status": "Finding 2",
            "f3_status": "Finding 3",
            "f4_status": "Finding 4",
            "f5_status": "Finding 5",
        }

        for key, val in rs.items():
            # Old->new name replacements (from verifier)
            if key.endswith("_replacements") and isinstance(val, list) and val:
                finding_key = key.replace("_replacements", "")
                status_key = finding_key + "_status"
                status = rs.get(status_key, "")
                label = finding_labels.get(status_key, finding_key.upper())
                replace_lines.append(f"\n[{label} -- {status}]")
                for r in val:
                    replace_lines.append(
                        f'  OLD: "{r.get("old")}"  ->  NEW: "{r.get("new")}"'
                        f'  ({r.get("context", "")})'
                    )

            # Phantom model names (Bug #1: Close models wrongly cited as Open)
            if key.endswith("_phantom_models") and isinstance(val, list) and val:
                banned.extend(val)

            # Bug #4: suppressed phrases from L1 sentences whose prerequisite reversed
            if key.endswith("_suppressed_phrases") and isinstance(val, list) and val:
                suppressed.extend(val)

            # Bug #1/2/3: mandatory notes added by reasoning guides
            if key.endswith("_MANDATORY_note") and isinstance(val, str) and val:
                mandatory_notes.append(val)

            # Bug #3: benchmark disambiguation warning
            if key == "f2_benchmark_warning" and isinstance(val, str) and val:
                mandatory_notes.append(val)

            # Bug #4: reversal note
            if key.endswith("_reversal_note") and isinstance(val, str) and val:
                mandatory_notes.append(val)

        banned = sorted(set(banned))
        suppressed = list(dict.fromkeys(suppressed))  # deduplicate, preserve order

        if not replace_lines and not banned and not suppressed and not mandatory_notes:
            return ""

        lines = ["### MANDATORY WRITING CONSTRAINTS",
                 "",
                 "CRITICAL: Read every rule below before writing a single word.",
                 ""]

        if mandatory_notes:
            lines += ["#### Data-Enforced Rules (computed from current benchmark data)"]
            for note in mandatory_notes:
                lines.append(f"- {note}")
            lines.append("")

        if replace_lines:
            lines += [
                "#### Model Name Replacements (apply exactly)",
                "Any sentence containing an OLD model name after replacement is WRONG.",
            ]
            lines.extend(replace_lines)
            lines.append("")

        if banned:
            lines += [
                "#### BANNED MODEL NAMES (must not appear as open-source low scorers)",
                "These models are Type=Close. DO NOT cite them as open-source examples.",
                "",
            ]
            for m in banned:
                lines.append(f"  - {m}")
            lines.append("")

        if suppressed:
            lines += [
                "#### SUPPRESSED PHRASES (trend has reversed — these sentences are now WRONG)",
                "The following phrases describe a trend that no longer holds in current data.",
                "DO NOT write these phrases. If they appear in the ground truth, skip or rewrite them.",
                "",
            ]
            for phrase in suppressed:
                lines.append(f'  - "{phrase}"')

        return "\n".join(lines)

    def _ground_truth_block(self) -> str:
        if not self.ground_truth:
            return ""

        findings = self.ground_truth.get("findings", [])
        if not findings:
            return ""

        lines = [
            "### Reference Findings (Human-Authored Report)",
            "",
            "Below are the findings from the original human-written report.",
            "Each sentence carries an internal stability classification that",
            "determines how you should handle it (DO NOT expose these",
            "classifications in your output — they are instructions to you only):",
            "",
            "- Sentences marked [STABLE] should be preserved verbatim when the",
            "  underlying data trend still holds. If the trend no longer holds,",
            "  drop the entire finding.",
            "- Sentences marked [ADAPT] should keep the original wording when",
            "  the trend is unchanged; adjust the wording when the trend shifts.",
            "- Sentences marked [REFRESH] must always be rewritten using the",
            "  latest data — update model names, rankings, dimensional emphasis,",
            "  etc. — but do NOT insert specific numerical scores.",
            "",
            "CRITICAL: When data trends have NOT changed, you MUST use the",
            "original human language as-is. Do NOT rephrase stable content.",
            "",
        ]

        for idx, finding in enumerate(findings, start=1):
            title = finding.get("title", "")
            lines.append(f"#### Finding {idx}: {title}")

            for sentence in finding.get("sentences", []):
                tier = sentence.get("tier", "?")
                text = sentence.get("text", "").strip()

                tag = {"A": "STABLE", "B": "ADAPT", "C": "REFRESH"}.get(tier, "?")
                lines.append(f"  [{tag}] {text}")

                rule_key = {
                    "A": "preservation_rule",
                    "B": "modification_rule",
                    "C": "regeneration_rule",
                }.get(tier, "")
                rule = sentence.get(rule_key, "").strip()
                if rule:
                    lines.append(f"    (Internal note: {rule})")
                lines.append("")

        exclusions = self.ground_truth.get("explicit_exclusions", [])
        if exclusions:
            lines.append("#### Exclusions")
            for exc in exclusions:
                lines.append(f"  - {exc}")

        return "\n".join(lines)

    def _data_change_block(self) -> str:
        """
        Render a compact, structured analytics block for the LLM prompt.
        """
        if self.analytics:
            return self._format_analytics_block()

        if not self.data_summary:
            return ""

        raw = str(self.data_summary)
        if len(raw) > 4000:
            raw = raw[:4000] + "\n... [truncated]"
        return (
            "### Current Data Summary\n"
            "Below is a summary of the current benchmark data. "
            "Use it to decide which findings to preserve, adapt, or refresh.\n\n"
            f"{raw}"
        )

    def _format_analytics_block(self) -> str:
        """Format structured analytics as a readable Markdown block."""
        lines = [
            "### Current Data Analytics",
            "",
            "The following structured analytics were computed from the new "
            "benchmark data.  Use these to drive your KEEP / ADAPT / REFRESH "
            "decisions for each finding.",
            "",
        ]

        a = self.analytics

        # --- Schwartz ---
        s = a.get("schwartz", {})
        if s and "error" not in s:
            lines.append("**Schwartz Value Dimensions**")
            ordered = s.get("dimension_ranking", {}).get("ordered", [])
            if ordered:
                lines.append(f"  Dimension order (high to low): {' > '.join(ordered)}")
            pan_ok = s.get("pan_cultural_order_holds", True)
            lines.append(f"  Pan-cultural order (top-4) intact: {pan_ok}")
            top5 = s.get("model_total_ranking", [])[:5]
            if top5:
                parts = [f"#{i+1} {m['model']} ({m.get('value','?')})"
                         for i, m in enumerate(top5)]
                lines.append(f"  Top models by total score: {', '.join(parts)}")
            leaders = s.get("dimension_leaders", {})
            # Handle both old format (str) and new format (dict with model/value/margin)
            for d in ["Self-direction", "Conformity", "Universalism", "Stimulation"]:
                info = leaders.get(d)
                if info:
                    if isinstance(info, dict):
                        margin_str = f", margin={info['margin']}" if info.get("margin") is not None else ""
                        runner_str = f", runner-up={info['runner_up']} ({info.get('runner_up_value', '?')})" if info.get("runner_up") else ""
                        lines.append(f"  {d} leader: {info['model']} ({info.get('value','?')}{margin_str}{runner_str})")
                    else:
                        lines.append(f"  {d} leader: {info}")
            lines.append("")

        # --- MFT ---
        m = a.get("mft", {})
        if m and "error" not in m:
            lines.append("**MFT (Moral Foundation Theory) — EVR: lower = better**")
            best = m.get("best_model")
            best_evr = m.get("best_evr_avg")
            runner = m.get("runner_up_model")
            runner_evr = m.get("runner_up_evr_avg")
            gap = m.get("top_runner_up_gap")
            if best:
                lines.append(f"  Best model (lowest EVR): {best} ({best_evr}%)")
            if runner:
                lines.append(f"  Runner-up: {runner} ({runner_evr}%), gap={gap:.1f} pp")
            top5 = m.get("model_ranking_by_evr_avg", [])[:5]
            if top5:
                parts = [f"#{i+1} {e['model']} ({e.get('value','?')}%)"
                         for i, e in enumerate(top5)]
                lines.append(f"  Top-5 (best first): {', '.join(parts)}")
            hard = m.get("hardest_dimensions", [])
            easy = m.get("easiest_dimensions", [])
            if hard:
                lines.append(f"  Hardest dims (highest EVR): {', '.join(hard)}")
            if easy:
                lines.append(f"  Easiest dims (lowest EVR): {', '.join(easy)}")
            evr_type = m.get("evr_by_type", {})
            if evr_type:
                lines.append("  EVR by model type: " +
                             "; ".join(f"{k}={v}%" for k, v in evr_type.items()))
            r_vs_n = m.get("reasoning_vs_normal_evr", {})
            if r_vs_n:
                lines.append(
                    f"  Reasoning vs Normal (MFT): "
                    f"Reasoning={r_vs_n.get('reasoning_mean_evr')}%, "
                    f"Normal={r_vs_n.get('normal_mean_evr')}% "
                    f"(reasoning better={r_vs_n.get('reasoning_better')})"
                )
            lines.append("")

        # --- Risk/Safety ---
        r = a.get("risk", {})
        if r and "error" not in r:
            lines.append("**Safety Taxonomy -- ASR: lower = safer**")
            pct = r.get("pct_models_above_90_safety")
            ceil = r.get("ceiling_effect")
            if pct is not None:
                lines.append(f"  Models above 90% safety: {pct}%  (ceiling={ceil})")
            top3 = r.get("top_safety_models", [])[:3]
            if top3:
                parts = [f"#{i+1} {e['model']} ({e.get('value','?')}%)"
                         for i, e in enumerate(top3)]
                lines.append(f"  Safest models: {', '.join(parts)}")
            cat_rank = r.get("category_ranking", {})
            if cat_rank:
                sorted_cats = sorted(cat_rank, key=lambda c: cat_rank[c], reverse=True)
                lines.append("  Category difficulty (hardest first): " +
                             " > ".join(sorted_cats))
            lines.append("")

        # --- FULVA ---
        f = a.get("fulva", {})
        if f and "error" not in f:
            lines.append("**FULVA -- User-oriented vs. counterpart dimensions**")
            pairs = f.get("pair_comparisons", [])
            for p in pairs:
                arrow = ">" if p.get("direction_holds") else "<  [REVERSED]"
                lines.append(
                    f"  {p.get('preferred_dim')} {arrow} counterpart | "
                    f"gap={p.get('gap','?')} | "
                    f"models w/ positive gap: {p.get('models_with_positive_gap')}"
                    f"/{p.get('total_models')}"
                )
            top3 = f.get("model_ranking", [])[:3]
            if top3:
                parts = [f"#{i+1} {e['model']} ({e.get('value','?')})"
                         for i, e in enumerate(top3)]
                lines.append(f"  Top models by avg FULVA score: {', '.join(parts)}")
            lines.append("")

        # --- Cross-framework validation ---
        cf = a.get("cross_framework", {})
        if cf:
            lines.append("**Cross-Framework Example Validation**")
            ov3 = cf.get("ov3_o3mini_example", {})
            if ov3:
                valid_str = "VALID" if ov3.get("still_valid") else "INVALID -- do NOT use"
                lines.append(f"  OV-3 o3-mini example: {valid_str} -- {ov3.get('reason', '')}")
            lines.append("")

        # --- Cross-section ---
        cs = a.get("cross_section", {})
        if cs and "error" not in cs:
            r_sch = cs.get("schwartz_reasoning_vs_normal", {})
            if r_sch:
                lines.append("**Cross-section: Reasoning vs. Normal (Schwartz total)**")
                lines.append(
                    f"  Reasoning={r_sch.get('reasoning_mean_total')}, "
                    f"Normal={r_sch.get('normal_mean_total')} "
                    f"(stronger={r_sch.get('reasoning_stronger')})"
                )
                lines.append("")
            s_type = cs.get("schwartz_by_type", {})
            if s_type:
                lines.append("**Schwartz total score by model type**")
                lines.append("  " + "; ".join(f"{k}={v}" for k, v in s_type.items()))
                lines.append("")

        # --- Newly added models ---
        new_models = a.get("newly_added_models", [])
        if new_models:
            lines.append("**Newly Added Models (not in baseline)**")
            lines.append(f"  {', '.join(new_models)}")
            lines.append("  IMPORTANT: Consider these models for top-N rankings and example replacements.")
            lines.append("")

        return "\n".join(lines)

    def _reasoning_block(self) -> str:
        if not self.reasoning_summary:
            return ""

        lines = [
            "### Writing Guidance (per Finding)",
            "",
            "For each finding, the STATUS tells you how to handle the original sentences:",
            "  KEEP              -> trend unchanged; use original language verbatim",
            "  ADAPT             -> trend direction holds but intensity shifted; adjust wording",
            "  REFRESH_EXAMPLES  -> core trend holds; replace model names / specific numbers",
            "  SIGNIFICANTLY_CHANGED -> flag for Mentor review; do not silently preserve",
            "  FREEZE            -> required data missing; preserve previous text; add footnote",
            "",
        ]

        rs = self.reasoning_summary

        if not isinstance(rs, dict):
            lines.append(str(rs))
            return "\n".join(lines)

        for key, val in rs.items():
            if key == "_section":
                continue
            if val is None or val == "" or val == [] or val == {}:
                continue
            if isinstance(val, list):
                val_str = ", ".join(str(v) for v in val)
            elif isinstance(val, dict):
                val_str = "; ".join(f"{k}={v}" for k, v in val.items())
            else:
                val_str = str(val)
            if key.endswith("_status"):
                lines.append(f"  [{key.upper()}] {val_str}")
            else:
                lines.append(f"  {key}: {val_str}")

        # Special handling for Overall F2 FREEZE footnote
        footnote = rs.get("f2_data_pending_footnote")
        if footnote:
            lines += [
                "",
                "IMPORTANT -- Finding 2 FREEZE instruction:",
                "  After all other findings, append the following footnote VERBATIM:",
                f"  {footnote}",
            ]

        return "\n".join(lines)

    def _new_insight_block(self) -> str:
        if not self.new_insights:
            return ""

        insights = "\n".join(f"- {i}" for i in self.new_insights)
        return (
            "### Candidate New Insights\n"
            "The following observations were identified from the current data "
            "but are not present in the original report. You may draw on them "
            "when composing the new exploratory findings at the end of this "
            "section.\n\n"
            f"{insights}"
        )

    def _writing_constraints(self) -> str:
        """
        Global writing constraints shared by all sections.
        """
        return (
            "### Writing Constraints\n"
            "\n"
            "**Output structure -- preserve the report's heading hierarchy:**\n"
            "- Keep the section heading (e.g. 'Schwartz Theory of Basic Values'\n"
            "  or '1. Overall Perspectives of LLM Value Evaluation').\n"
            "- Keep each 'Finding N: <title>' as a visible sub-heading.\n"
            "- IMPORTANT: Insert ONE blank line after each 'Finding N: <title>'\n"
            "  heading before the body text begins.\n"
            "- Under each finding, write the body as coherent, flowing paragraphs\n"
            "  -- the same style as the original human report.\n"
            "- Do NOT merge finding titles into body paragraphs.\n"
            "\n"
            "**CRITICAL content rule:**\n"
            "- If the first sentence of the body text is identical (in meaning or\n"
            "  wording) to the finding title, REPHRASE that first sentence using\n"
            "  different language while preserving the exact same meaning.\n"
            "  For example:\n"
            "    Title: 'Models exhibit consistent value preferences'\n"
            "    First sentence should NOT start with: 'Models exhibit...'\n"
            "    Instead, try: 'LLMs demonstrate remarkable alignment in their...' or\n"
            "    'Across the tested architectures, value preferences remain...' etc.\n"
            "\n"
            "**Content rules:**\n"
            "- Do NOT use bullet points, numbered lists, or any internal labels\n"
            "  (e.g. 'Argument:', 'Evidence:', 'Explanation:', 'Tier A/B/C',\n"
            "  'STABLE', 'ADAPT', 'REFRESH') in the output body.\n"
            "- Do NOT cite specific numerical scores, percentages, or exact\n"
            "  metric values. Instead use qualitative comparative language\n"
            "  (e.g. 'significantly outperform', 'score notably higher',\n"
            "  'achieve near-perfect scores', 'the gap widens').\n"
            "- When data trends are unchanged, reproduce the original human\n"
            "  text verbatim. Do NOT rephrase stable content.\n"
            "- Focus on interpretation, comparison, and implications rather\n"
            "  than chart descriptions or raw data.\n"
            "- Avoid speculative causal claims unless clearly hedged.\n"
            "- Maintain the human report's analytical depth and tone.\n"
            "- Use the INTENSITY LANGUAGE CALIBRATION values from the Global\n"
            "  Pipeline Signals section above (if present) for group comparisons.\n"
            "\n"
            "**New findings:**\n"
            "- After all preserved / adapted findings, append 1-2 NEW\n"
            "  exploratory findings derived from the current data that were\n"
            "  not in the original report. Format them EXACTLY as:\n"
            "  '*NEW* Finding N: <title>'\n"
            "  The '*NEW*' prefix -- written with asterisk (*) characters -- MUST\n"
            "  appear verbatim at the start of each new finding title line so it\n"
            "  can be highlighted and reviewed in the final report.\n"
            "  Every new finding MUST begin with the '*NEW*' token.\n"
            "  A finding added without the '*NEW*' marker will be treated as\n"
            "  human-original text, which is INCORRECT.\n"
        )

    # ---------- LLM call ----------

    def call_llm(self, prompt: str) -> str:
        """
        Call Azure OpenAI to generate section text.
        Override this method in tests or for local development with a mock.
        """
        from src.pipeline.aoai_client import chat_completion

        messages = [
            {"role": "system", "content": (
                "You are a senior research analyst writing one section of the "
                "Value Compass report. Follow the internal stability tags "
                "(STABLE / ADAPT / REFRESH) to decide how to handle each "
                "sentence, but NEVER expose those tags in the final text. "
                "Preserve the report's heading hierarchy -- section heading "
                "and 'Finding N:' sub-headings must appear as-is. Under each "
                "finding, write the body as natural, flowing paragraphs. "
                "Every new finding you add MUST start with '*NEW*' prefix."
            )},
            {"role": "user", "content": prompt},
        ]
        return chat_completion(messages)

    # ---------- Post-processing ----------

    def postprocess(self, text: str) -> str:
        """
        Post-processing: strip whitespace.
        """
        return text.strip()
