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

        # --- OV-1 Spearman alignment stats ---
        n_well   = s.get("n_well_aligned_models", 0)
        n_total  = s.get("n_total_models_spearman", 0)
        pct_well = s.get("well_aligned_model_pct", 0)
        mean_rho = s.get("mean_model_baseline_spearman")
        agg_rho  = s.get("aggregate_baseline_spearman")

        # Human-readable summary: "X / Y models (Z%) are well-aligned (Spearman > 0.7)"
        if n_total > 0:
            f1_alignment_summary = (
                f"{n_well}/{n_total} models ({pct_well}%) have Spearman > 0.7 "
                f"with the pan-cultural baseline "
                f"(mean Spearman={mean_rho}, aggregate Spearman={agg_rho})"
            )
            f1_majority_aligned = pct_well >= 50.0
        else:
            f1_alignment_summary = "(Spearman data unavailable)"
            f1_majority_aligned  = True  # default: preserve existing claim

        # Well-aligned models that also have Uni/Ben/Sec in top-4
        safety_top = s.get("models_with_safety_dims_in_top4", [])

        return {
            # Finding 1 — Schwartz ordering
            "f1_status":           f1.get("status", "KEEP"),
            "f1_dimension_order":  s.get("dimension_ranking", {}).get("ordered", []),
            "f1_pan_cultural_holds": s.get("pan_cultural_order_holds", True),
            "f1_safety_dim_leaders": _fmt_models(s.get("safety_dim_leaders", [])),
            "f1_alignment_summary":  f1_alignment_summary,
            "f1_majority_aligned":   f1_majority_aligned,
            "f1_well_aligned_models": _fmt_list(s.get("well_aligned_models", [])[:6]),
            "f1_safety_top_models":   _fmt_list(safety_top[:6]),
            "f1_pan_cultural_baseline": (
                "Human baseline order: Universalism > Benevolence > Self-Direction > Security "
                "> Conformity > Achievement > Tradition > Stimulation > Hedonism > Power"
            ),

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

        result = {
            "f1_status":          f1.get("status", "REFRESH_EXAMPLES"),
            "f1_dimension_order": ordered,
            "f1_dim_leaders":     leader_lines,
            "f1_notable_models": (
                f"Self-direction leader: {leaders.get('Self-direction', {}).get('model')}; "
                f"Conformity leader: {leaders.get('Conformity', {}).get('model')}; "
                f"Universalism leader: {leaders.get('Universalism', {}).get('model')}"
            ),

            "f2_status":     f2.get("status", "REFRESH_EXAMPLES"),
            "f2_top3":       _fmt_models(s.get("model_total_ranking", [])[:3]),
            "f2_full_rank":  _fmt_models(s.get("model_total_ranking", []), max_n=6),
        }

        # Surface title qualifier note when leaders have changed substantially
        qualifier_note = f1.get("title_qualifier_note")
        if qualifier_note:
            result["f1_title_qualifier_note"] = qualifier_note

        return result

    # ------------------------------------------------------------------ mft
    def _guide_mft(
        self,
        analytics: Dict[str, Any],
        changes:   Dict[str, Any],
    ) -> Dict[str, Any]:
        m  = analytics.get("mft", {})
        f1 = changes.get("mft_f1", {})
        f2 = changes.get("mft_f2", {})

        # Summarise per-model weak dims for family-level patterns
        weak_dims = m.get("model_weak_dimensions", {})
        # Group by weak dimension
        dim_to_models: Dict[str, List[str]] = {}
        for model, dim in weak_dims.items():
            dim_to_models.setdefault(dim, []).append(model)
        family_weak_summary = "; ".join(
            f"{dim}: {', '.join(models[:3])}"
            for dim, models in list(dim_to_models.items())[:4]
        )

        return {
            "f1_status":       f1.get("status", "REFRESH_EXAMPLES"),
            "f1_best_model":   m.get("best_model"),
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

        result = {
            "f1_status":       f1.get("status", "KEEP"),
            "f1_bias_holds":   f.get("user_oriented_bias_holds", True),
            "f1_pair_summary": pair_summary,

            "f2_status":     f2.get("status", "REFRESH_EXAMPLES"),
            "f2_top_models": _fmt_models(f.get("model_ranking", [])[:3]),
        }

        if f1.get("weaken_ethical_professional"):
            result["f1_weaken_ethical_professional"] = True
            result["f1_weaken_reason"] = f1.get("reason", "")

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

        open_low_scorers = cs.get("open_low_scorers", [])

        return {
            "f1_status":          f1.get("status", "KEEP"),
            "f1_evr_by_type":     evr_summary,
            "f1_gap_note":        f1.get("reason", ""),

            "f2_status":          f2.get("status", "REFRESH_EXAMPLES"),
            "f2_schwartz_by_type": schwartz_summary,
            "open_low_scorers":   open_low_scorers,
        }

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

        f1 = changes.get("families_f1", {})
        f2 = changes.get("families_f2", {})

        consistent  = f1.get("consistent_families", [])
        diverging   = f1.get("diverging_families",  [])

        result = {
            "f1_status":          f1.get("status", "REFRESH_EXAMPLES"),
            "f1_note":            f1.get("reason", ""),
            "f2_status":          f2.get("status", "REFRESH_EXAMPLES"),
            "family_summary":     family_summary,
            "consistent_families": consistent,
        }

        if diverging:
            result["diverging_families"] = diverging
            result["major_diverging"]    = f1.get("major_diverging_families", [])

        return result

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
