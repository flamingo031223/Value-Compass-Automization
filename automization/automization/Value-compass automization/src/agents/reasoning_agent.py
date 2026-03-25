"""
Per-section / per-finding reasoning agent.

Translates structured analytics + finding-change statuses into
actionable, human-readable writing guidance for each section writer.

The guidance is formatted as a structured dict and rendered as a
compact Markdown block inside the LLM prompt.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_list(items: List[Any], max_items: int = 5) -> str:
    """Format a list as a compact comma-separated string."""
    strs = [str(i) for i in items[:max_items]]
    return ", ".join(strs) if strs else "(none)"


def _fmt_models(ranking: List[Dict], max_n: int = 5) -> str:
    """Format a model ranking list as '#1 ModelA, #2 ModelB, ...'"""
    parts = []
    for i, entry in enumerate(ranking[:max_n], start=1):
        name = entry.get("model", "?")
        val  = entry.get("value", entry.get("avg_score", entry.get("total", "?")))
        parts.append(f"#{i} {name} ({val})")
    return ", ".join(parts) if parts else "(no data)"


# ---------------------------------------------------------------------------
# ReasoningAgent
# ---------------------------------------------------------------------------

class ReasoningAgent:
    """
    Produces per-section writing guidance from analytics + change status.

    Two interfaces:
      reason()             — legacy, accepts ground_truth + change_summary
      reason_for_section() — new, section-aware, produces richer guidance
    """

    # ------------------------------------------------------------------ legacy
    def reason(
        self,
        ground_truth: Dict[str, Any],
        change_summary: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Legacy interface kept for backwards compatibility.
        Returns a flat guidance dict.
        """
        statuses = [
            v.get("status", "KEEP")
            for v in change_summary.values()
            if isinstance(v, dict)
        ]
        n_changed = sum(1 for s in statuses if s == "SIGNIFICANTLY_CHANGED")
        stable = n_changed == 0

        return {
            "reuse_core_conclusions":    stable,
            "reuse_medium_insights":     stable,
            "dimensions_to_reconsider":  change_summary.get("changed_dimensions", []),
            "models_to_highlight":       change_summary.get("notable_model_shifts", []),
            "finding_changes":           change_summary,
        }

    # ------------------------------------------------------------------ new
    def reason_for_section(
        self,
        section_key: str,
        analytics:   Dict[str, Any],
        finding_changes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Produce richly-structured writing guidance for one section.

        The returned dict is serialised to Markdown in
        BaseSectionWriter._reasoning_block().
        """
        DISPATCH = {
            "overall_findings": self._guide_overall,
            "schwartz":         self._guide_schwartz,
            "mft":              self._guide_mft,
            "safety":           self._guide_safety,
            "fulva":            self._guide_fulva,
            "open_closed":      self._guide_open_closed,
            "model_families":   self._guide_families,
            "reasoning":        self._guide_reasoning,
        }
        fn = DISPATCH.get(section_key, self._guide_generic)
        guidance = fn(analytics, finding_changes)
        guidance["_section"] = section_key

        # Propagate verifier replacement instructions into the reasoning summary
        # so base_section_writer._replacement_instructions_block() can render them
        guidance = self._merge_verifier_data(guidance, section_key, finding_changes)

        return guidance

    def _merge_verifier_data(
        self,
        result: Dict[str, Any],
        section_key: str,
        finding_changes: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge verifier replacement data (replacements, phantom_models, key_facts)
        from finding_changes into the reasoning result dict.
        Maps finding IDs to their f-number keys for the section.
        """
        # Map section keys to relevant finding IDs
        section_to_findings = {
            "overall_findings": ["overall_f1", "overall_f2", "overall_f3", "overall_f4", "overall_f5"],
            "schwartz":         ["schwartz_f1", "schwartz_f2"],
            "mft":              ["mft_f1", "mft_f2"],
            "safety":           ["safety_f1", "safety_f2"],
            "fulva":            ["fulva_f1", "fulva_f2"],
            "open_closed":      ["propclosed_f1", "propclosed_f2"],
            "model_families":   ["families_f1", "families_f2"],
            "reasoning":        ["reasoning_f1", "reasoning_f2"],
        }
        finding_ids = section_to_findings.get(section_key, [])

        for i, fid in enumerate(finding_ids, start=1):
            fc = finding_changes.get(fid, {})
            replacements = fc.get("replacements", [])
            phantoms = fc.get("phantom_models", [])
            key_facts = fc.get("key_facts", {})

            if replacements:
                result[f"f{i}_replacements"] = replacements
            if phantoms:
                result[f"f{i}_phantom_models"] = phantoms
            if key_facts:
                result[f"f{i}_key_facts"] = key_facts

        return result

    # ------------------------------------------------------------------ overall
    def _guide_overall(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        s = analytics.get("schwartz", {})
        m = analytics.get("mft",     {})
        r = analytics.get("risk",    {})

        f1 = changes.get("overall_f1", {})
        f2 = changes.get("overall_f2", {})
        f3 = changes.get("overall_f3", {})
        f4 = changes.get("overall_f4", {})

        return {
            # Finding 1 — Schwartz ordering
            "f1_status":           f1.get("status", "KEEP"),
            "f1_dimension_order":  s.get("dimension_ranking", {}).get("ordered", []),
            "f1_pan_cultural_holds": s.get("pan_cultural_order_holds", True),
            "f1_safety_dim_leaders": _fmt_models(s.get("safety_dim_leaders", [])),

            # Finding 2 — Western bias (FREEZE)
            "f2_status":           "FREEZE",
            "f2_instruction":      f2.get("reason", ""),
            "f2_data_pending_footnote": f2.get("data_pending_footnote", ""),

            # Finding 3 — Cross-framework correlation
            "f3_status":           f3.get("status", "REFRESH_EXAMPLES"),
            "f3_self_dir_leader":  f3.get("self_direction_leader"),
            "f3_conformity_leader": f3.get("conformity_leader"),
            "f3_mft_best_model":   f3.get("mft_best_model"),
            "f3_mft_hardest_dims": _fmt_list(f3.get("mft_hardest_dims", [])),

            # Finding 4 — Static ceiling
            "f4_status":            f4.get("status", "REFRESH_EXAMPLES"),
            "f4_top_safety_models": _fmt_models(f4.get("top_safety_models",
                                                        r.get("top_safety_models", []))),
            "f4_best_mft_model":    f4.get("best_mft_model", m.get("best_model")),
            "f4_best_evr":          f4.get("best_evr_avg",  m.get("best_evr_avg")),

            # Finding 5 — Context-aware safety
            "f5_status": "KEEP",
        }

    # ------------------------------------------------------------------ schwartz
    def _guide_schwartz(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        s  = analytics.get("schwartz", {})
        f1 = changes.get("schwartz_f1", {})
        f2 = changes.get("schwartz_f2", {})

        leaders = s.get("dimension_leaders", {})
        ordered = s.get("dimension_ranking", {}).get("ordered", [])

        # Build per-dimension leader summary
        leader_lines = []
        for dim, info in leaders.items():
            if info:
                leader_lines.append(f"{dim}: {info.get('model')} ({info.get('value')})")

        # Bug #2 fix: provide authoritative top-3 for F2 as explicit replacement directives.
        # The LLM must use these exact names — no approximation.
        top3_entries = s.get("model_total_ranking", [])[:3]
        top3_names   = [e["model"] for e in top3_entries]
        top3_auth_str = ", ".join(
            f"{e['model']} (total={e.get('value', '?')})" for e in top3_entries
        )

        # Bug #4 fix: when Schwartz hierarchy is SIGNIFICANTLY_CHANGED, suppress
        # any sentence that asserts the old pan-cultural ordering as still valid.
        suppressed_phrases: List[str] = []
        if f1.get("status") == "SIGNIFICANTLY_CHANGED":
            suppressed_phrases = [
                "Universalism, Benevolence, Security, and Self-Direction consistently emerge",
                "prioritize Universalism",
                "reflecting a hierarchy that mirrors pan-cultural human value surveys",
                "a hierarchical order similar to the pan-cultural baseline",
            ]

        result: Dict[str, Any] = {
            "f1_status":          f1.get("status", "REFRESH_EXAMPLES"),
            "f1_dimension_order": ordered,
            "f1_dim_leaders":     leader_lines,
            "f1_notable_models": (
                f"Self-direction leader: {leaders.get('Self-direction', {}).get('model')}; "
                f"Conformity leader: {leaders.get('Conformity', {}).get('model')}; "
                f"Universalism leader: {leaders.get('Universalism', {}).get('model')}"
            ),

            "f2_status":                  f2.get("status", "REFRESH_EXAMPLES"),
            "f2_top3":                    _fmt_models(top3_entries),
            "f2_full_rank":               _fmt_models(s.get("model_total_ranking", []), max_n=6),
            # Bug #2: authoritative top-3 — LLM must use exactly these names in F2
            "f2_top3_authoritative":      top3_auth_str,
            "f2_top3_names_only":         ", ".join(top3_names),
            "f2_MANDATORY_note": (
                f"Finding 2 MUST name exactly these top-3 models: {', '.join(top3_names)}. "
                "Do NOT use any other model names as 'top performers' in this finding."
            ),
        }
        if suppressed_phrases:
            result["f1_suppressed_phrases"] = suppressed_phrases
        return result

    # ------------------------------------------------------------------ mft
    def _guide_mft(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        m  = analytics.get("mft", {})
        r  = analytics.get("risk", {})
        f1 = changes.get("mft_f1", {})
        f2 = changes.get("mft_f2", {})

        # Summarise per-model weak dims for family-level patterns
        weak_dims = m.get("model_weak_dimensions", {})
        dim_to_models: Dict[str, List[str]] = {}
        for model, dim in weak_dims.items():
            dim_to_models.setdefault(dim, []).append(model)
        family_weak_summary = "; ".join(
            f"{dim}: {', '.join(models[:3])}"
            for dim, models in list(dim_to_models.items())[:4]
        )

        # Bug #3 fix: explicitly identify MFT champion vs. Safety champion
        # so they cannot be swapped. These come from different sheets.
        mft_best   = m.get("best_model", "")       # lowest EVR — from MFT sheet
        safety_top = r.get("top_safety_models", [])
        safety_best = safety_top[0]["model"] if safety_top else ""  # from Risk sheet

        return {
            "f1_status":       f1.get("status", "REFRESH_EXAMPLES"),
            "f1_best_model":   mft_best,
            "f1_best_evr":     m.get("best_evr_avg"),
            "f1_runner_up":    m.get("runner_up_model"),
            "f1_runner_up_evr": m.get("runner_up_evr_avg"),
            "f1_gap_pp":       m.get("top_runner_up_gap"),
            "f1_large_gap":    m.get("large_gap", False),
            "f1_top_ranking":  _fmt_models(m.get("model_ranking_by_evr_avg", []), max_n=5),

            "f2_status":            f2.get("status", "REFRESH_EXAMPLES"),
            "f2_hardest_dims":      _fmt_list(m.get("hardest_dimensions", [])),
            "f2_easiest_dims":      _fmt_list(m.get("easiest_dimensions", [])),
            "f2_family_weak_dims":  family_weak_summary,
            "f2_dim_evr_means":     m.get("dimension_evr_means", {}),
            # Bug #3: explicit guard — MFT and Safety champions are DIFFERENT models
            "f2_mft_champion":      mft_best,
            "f2_benchmark_warning": (
                f"CRITICAL: MFT champion (lowest EVR) = '{mft_best}'. "
                f"Safety Taxonomy champion (highest safety score) = '{safety_best}'. "
                f"These are TWO DIFFERENT models from TWO DIFFERENT benchmarks. "
                f"MFT findings (F1, F2) MUST use '{mft_best}', NOT '{safety_best}'. "
                f"Safety findings use '{safety_best}'. Never swap them."
            ),
        }

    # ------------------------------------------------------------------ safety
    def _guide_safety(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        r  = analytics.get("risk", {})
        f1 = changes.get("safety_f1", {})
        f2 = changes.get("safety_f2", {})

        cat_rank = r.get("category_ranking", {})
        sorted_cats = sorted(cat_rank, key=lambda c: cat_rank.get(c, 0), reverse=True)

        return {
            "f1_status":         f1.get("status", "KEEP"),
            "f1_pct_above_90":   r.get("pct_models_above_90_safety"),
            "f1_ceiling_holds":  r.get("ceiling_effect", True),
            "f1_top_models":     _fmt_models(r.get("top_safety_models", []), max_n=3),

            "f2_status":             f2.get("status", "KEEP"),
            "f2_hardest_categories": _fmt_list(r.get("hardest_categories", [])),
            "f2_easiest_categories": _fmt_list(r.get("easiest_categories", [])),
            "f2_full_category_order": " > ".join(sorted_cats),
        }

    # ------------------------------------------------------------------ fulva
    def _guide_fulva(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        f  = analytics.get("fulva", {})
        f1 = changes.get("fulva_f1", {})
        f2 = changes.get("fulva_f2", {})

        pairs = f.get("pair_comparisons", [])
        pair_summary = "; ".join(
            f"{p['pair']}: gap={p.get('gap', '?')} ({'holds' if p.get('direction_holds') else 'REVERSED'})"
            for p in pairs
        )

        result: Dict[str, Any] = {
            "f1_status":       f1.get("status", "KEEP"),
            "f1_bias_holds":   f.get("user_oriented_bias_holds", True),
            "f1_pair_summary": pair_summary,

            "f2_status":     f2.get("status", "REFRESH_EXAMPLES"),
            "f2_top_models": _fmt_models(f.get("model_ranking", [])[:3]),
        }

        # Bug #4 fix: when user-oriented bias has REVERSED, the L1 sentence
        # "While this tendency may enhance user-perceived helpfulness..." describes
        # a tendency that no longer exists. Suppress it to prevent contradiction.
        if f1.get("status") == "SIGNIFICANTLY_CHANGED" and not f.get("user_oriented_bias_holds", True):
            result["f1_suppressed_phrases"] = [
                "While this tendency may enhance user-perceived helpfulness",
                "this tendency may enhance user-perceived helpfulness and friendliness",
                "it also introduces potential risks\u2014such as generating hallucinated responses",
                "user-oriented values",
                "prioritizing user-oriented",
                "user-oriented bias",
            ]
            result["f1_reversal_note"] = (
                "The user-oriented bias has REVERSED. Any sentence describing "
                "'this tendency' (user-oriented preference) as still present is "
                "FACTUALLY WRONG. Delete or rewrite those sentences. Do NOT write "
                "'While this tendency may enhance helpfulness...' when the tendency "
                "no longer exists in the data."
            )

        return result

    # ------------------------------------------------------------------ open_closed
    def _guide_open_closed(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        m  = analytics.get("mft", {})
        cs = analytics.get("cross_section", {})
        f1 = changes.get("propclosed_f1", {})
        f2 = changes.get("propclosed_f2", {})

        evr_by_type = m.get("evr_by_type", {})
        evr_summary = "; ".join(f"{k}: EVR={v}" for k, v in evr_by_type.items())

        by_type_schwartz = cs.get("schwartz_by_type", {})
        schwartz_summary = "; ".join(
            f"{k}: Schwartz_total={v}" for k, v in by_type_schwartz.items()
        )

        # Bug #1 fix: provide type-validated open-source low scorers from Model Info.
        # These are the ONLY models that can be cited as 'open-source low scorers' in F2.
        open_low = analytics.get("open_low_scorers", [])
        open_low_names = [e["model"] for e in open_low]
        open_low_str = ", ".join(
            f"{e['model']} (total={e.get('schwartz_total', '?')})" for e in open_low
        )

        result: Dict[str, Any] = {
            "f1_status":          f1.get("status", "KEEP"),
            "f1_evr_by_type":     evr_summary,
            "f1_gap_note":        f1.get("reason", ""),

            "f2_status":           f2.get("status", "REFRESH_EXAMPLES"),
            "f2_schwartz_by_type": schwartz_summary,
            # Bug #1: type-validated open low scorers
            "f2_open_low_scorers": open_low_str if open_low_str else "(none found)",
            "f2_MANDATORY_note": (
                f"Finding 2 MUST cite open-source models as low scorers ONLY from this "
                f"type-validated list (Type=Open confirmed via Model Info): {open_low_str}. "
                "DO NOT cite GPT-4-Turbo, Claude-3.5-Sonnet, GLM-4, or any other "
                "Close-type model as an 'open-source low scorer'. "
                "Verify every model you name is actually Type=Open."
            ),
        }

        # Add phantom models: Close-type models that should never appear as open-source examples
        # These are the known Close models that have appeared incorrectly in past reports.
        known_close_phantom = []
        if any("gpt-4-turbo" in m["model"].lower() for m in open_low) is False:
            known_close_phantom += ["GPT-4-Turbo"]
        if any("claude" in m["model"].lower() for m in open_low) is False:
            known_close_phantom += ["Claude-3.5-Sonnet", "Claude-3.5-Haiku"]
        if any("glm" in m["model"].lower() for m in open_low) is False:
            known_close_phantom += ["GLM-4"]
        if known_close_phantom:
            result["f2_phantom_models"] = known_close_phantom

        return result

    # ------------------------------------------------------------------ families
    def _guide_families(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        cs = analytics.get("cross_section", {})
        families = cs.get("model_families", {})

        # Group models by developer
        dev_groups: Dict[str, List[str]] = {}
        for model, dev in families.items():
            dev_groups.setdefault(str(dev), []).append(str(model))

        family_summary = "; ".join(
            f"{dev}: {', '.join(models[:4])}"
            for dev, models in list(dev_groups.items())[:6]
        )

        return {
            "f1_status": "REFRESH_EXAMPLES",
            "f2_status": "REFRESH_EXAMPLES",
            "family_summary": family_summary,
            "instruction": (
                "Update all model family examples using the current model list above. "
                "Preserve the core finding that intra-family variance < inter-family variance."
            ),
        }

    # ------------------------------------------------------------------ reasoning
    def _guide_reasoning(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        m  = analytics.get("mft", {})
        cs = analytics.get("cross_section", {})
        f1 = changes.get("reasoning_f1", {})
        f2 = changes.get("reasoning_f2", {})

        mft_r_vs_n = m.get("reasoning_vs_normal_evr", {})
        sch_r_vs_n = cs.get("schwartz_reasoning_vs_normal", {})

        def _evr_str(d: Dict) -> str:
            if not d:
                return "(no data)"
            r = d.get("reasoning_mean_evr", "?")
            n = d.get("normal_mean_evr", "?")
            better = d.get("reasoning_better", False)
            return (f"Reasoning EVR={r}%, Normal EVR={n}% "
                    f"({'reasoning BETTER — lower EVR' if better else 'reasoning NOT better'})")

        def _sch_str(d: Dict) -> str:
            if not d:
                return "(no data)"
            r = d.get("reasoning_mean_total", "?")
            n = d.get("normal_mean_total", "?")
            stronger = d.get("reasoning_stronger", False)
            return (f"Reasoning total={r}, Normal total={n} "
                    f"({'reasoning stronger' if stronger else 'reasoning NOT stronger'})")

        return {
            "f1_status":           f1.get("status", "REFRESH_EXAMPLES"),
            "f1_mft_comparison":   _evr_str(mft_r_vs_n),
            "f1_instruction": (
                "Update model-specific examples (within-family comparisons like "
                "o3-mini vs GPT-4o, DeepSeek-R1 vs DeepSeek-V3) with current data."
            ),

            "f2_status":             f2.get("status", "KEEP"),
            "f2_schwartz_comparison": _sch_str(sch_r_vs_n),
        }

    # ------------------------------------------------------------------ generic
    def _guide_generic(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        return {"note": "No specialized guidance available for this section."}
