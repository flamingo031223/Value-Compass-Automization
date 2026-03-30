"""
Finding-specific data change detector.

Takes a structured analytics dict (from compute_all_analytics) and produces
a per-finding status for all 19 findings.  The status drives whether the
section writers should KEEP, ADAPT, REFRESH_EXAMPLES, or flag a
SIGNIFICANTLY_CHANGED finding for Mentor review.

Status values
-------------
KEEP                : Trend is unchanged; preserve all stable sentences verbatim.
ADAPT               : Direction holds but emphasis/gap shifted; adjust wording.
REFRESH_EXAMPLES    : Core trend holds; update model names / specific examples.
SIGNIFICANTLY_CHANGED : Core trend reversed; flag for Mentor review.
FREEZE              : Required external data missing; preserve previous text as-is.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Legacy simple detector (kept for backwards-compatibility with tests)
# ---------------------------------------------------------------------------

import numpy as np


def _summarize_records(records):
    if not records:
        return {}
    numeric_sums: Dict[str, list] = {}
    for rec in records:
        for k, v in rec.items():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                numeric_sums.setdefault(k, []).append(float(v))
    return {k: float(np.mean(vals)) for k, vals in numeric_sums.items()}


class SimpleDataChangeDetector:
    """Legacy interface — wraps FindingChangeDetector for backwards compatibility."""

    def detect_changes(
        self,
        new_data: Any,
        old_data: Any,
    ) -> Dict[str, Any]:
        changes: Dict[str, str] = {}
        for section, value in new_data.items():
            metrics = _summarize_records(value) if isinstance(value, list) else (
                value if isinstance(value, dict) else {}
            )
            old_value = old_data.get(section, {}) if isinstance(old_data, dict) else {}
            prev = _summarize_records(old_value) if isinstance(old_value, list) else (
                old_value if isinstance(old_value, dict) else {}
            )
            for k, v in metrics.items():
                prev_v = prev.get(k)
                path = f"{section}.{k}"
                if prev_v is None:
                    changes[path] = "new"
                else:
                    changes[path] = "needs_update" if abs(v - prev_v) > 0.05 else "unchanged"
        return changes


# ---------------------------------------------------------------------------
# Finding-specific change detector
# ---------------------------------------------------------------------------

class FindingChangeDetector:
    """
    Produces a per-finding status dict from structured analytics.

    Usage::

        analytics = compute_all_analytics(df_dict)
        detector  = FindingChangeDetector()
        changes   = detector.detect(analytics, old_analytics=baseline_analytics)
        # changes["overall_f1"] == {"status": "KEEP", ...}
    """

    # Thresholds
    MFT_LARGE_GAP_PP     = 10.0   # >10 pp between #1 and #2 = clear dominance
    MFT_TYPE_GAP_PP      = 5.0    # >5 pp between open/closed = meaningful gap
    SAFETY_CEILING_PCT   = 70.0   # >70% models above 90 safety = ceiling effect
    SCHWARTZ_TOP4_NEEDED = 3      # at least 3 of 4 expected dims in actual top-4
    MIN_LEADERSHIP_MARGIN = 0.05  # minimum score margin to consider a leadership change meaningful

    def detect(
        self,
        new_analytics: Dict[str, Any],
        old_analytics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Return a flat dict mapping finding_id -> {status, reason, ...}."""
        changes: Dict[str, Any] = {}

        # ---- Part 1: Overall findings (F1-F5) ----
        changes["overall_f1"] = self._overall_f1_schwartz_order(new_analytics, old_analytics)
        changes["overall_f2"] = self._overall_f2_western_bias()
        changes["overall_f3"] = self._overall_f3_cross_framework(new_analytics)
        changes["overall_f4"] = self._overall_f4_static_ceiling(new_analytics)
        changes["overall_f5"] = {
            "status": "KEEP",
            "reason": "Methodological conclusion; no quantitative trigger.",
        }

        # ---- Part 2: Schwartz findings ----
        changes["schwartz_f1"] = self._schwartz_f1_pan_cultural(new_analytics, old_analytics)
        changes["schwartz_f2"] = self._schwartz_f2_pronounced(new_analytics, old_analytics)

        # ---- Part 2: MFT findings ----
        changes["mft_f1"] = self._mft_f1_aligned_outperform(new_analytics)
        changes["mft_f2"] = self._mft_f2_dim_variation(new_analytics)

        # ---- Part 2: Safety findings ----
        changes["safety_f1"] = self._safety_f1_ceiling(new_analytics)
        changes["safety_f2"] = self._safety_f2_categories(new_analytics)

        # ---- Part 2: FULVA findings ----
        changes["fulva_f1"] = self._fulva_f1_user_bias(new_analytics)
        changes["fulva_f2"] = self._fulva_f2_top_models(new_analytics, old_analytics)

        # ---- Part 2: Proprietary vs. Open findings ----
        changes["propclosed_f1"] = self._prop_f1_mft_gap(new_analytics, old_analytics)
        changes["propclosed_f2"] = self._prop_f2_schwartz_gap(new_analytics)

        # ---- Part 2: Family findings ----
        changes["families_f1"] = self._families_f1_consistency(new_analytics)
        changes["families_f2"] = {
            "status": "REFRESH_EXAMPLES",
            "reason": "Inter/intra-family contrast examples must use current data.",
        }

        # ---- Part 2: Reasoning findings ----
        changes["reasoning_f1"] = self._reasoning_f1_safety(new_analytics, old_analytics)
        changes["reasoning_f2"] = self._reasoning_f2_schwartz(new_analytics)

        return changes

    def detect_with_verifications(
        self,
        new_analytics: Dict[str, Any],
        old_analytics: Optional[Dict[str, Any]] = None,
        verifications: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Enhanced detect that merges classic status with verifier replacement instructions.
        If verifications are provided, the verifier's status takes precedence for
        REWRITE/FREEZE/DELETE cases, and replacements are merged in.
        """
        changes = self.detect(new_analytics, old_analytics)

        if not verifications:
            return changes

        for finding_id, verif in verifications.items():
            if finding_id not in changes:
                changes[finding_id] = {}

            verif_status = verif.get("status")
            existing = changes[finding_id]

            # Verifier REWRITE/DELETE/FREEZE always override the classic status
            if verif_status in ("REWRITE", "DELETE", "FREEZE"):
                existing["status"] = verif_status
            elif verif_status == "REPLACE_MODEL" and existing.get("status") not in ("REWRITE", "DELETE", "FREEZE"):
                # Upgrade to REPLACE_MODEL unless already more severe
                existing["status"] = "REPLACE_MODEL"

            # Merge in replacement instructions and key_facts
            existing["replacements"] = verif.get("replacements", [])
            existing["key_facts"]    = verif.get("key_facts", {})
            existing["phantom_models"] = verif.get("phantom_models", [])
            if verif.get("notes"):
                existing["verifier_notes"] = verif["notes"]

        return changes

    # ------------------------------------------------------------------
    # Global signal extraction
    # ------------------------------------------------------------------

    def extract_global_signals(self, finding_changes: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract global signals that must broadcast to ALL section writers.
        A reversal in one section invalidates related claims in other sections.
        """
        schwartz_reversed = (
            finding_changes.get("schwartz_f1", {}).get("status") == "SIGNIFICANTLY_CHANGED"
            or finding_changes.get("overall_f1", {}).get("status") == "SIGNIFICANTLY_CHANGED"
        )
        fulva_reversed = (
            finding_changes.get("fulva_f1", {}).get("status") == "SIGNIFICANTLY_CHANGED"
        )
        ceiling_weakened = (
            finding_changes.get("safety_f1", {}).get("status") in
            ("SIGNIFICANTLY_CHANGED", "ADAPT")
        )
        reasoning_now_better = (
            finding_changes.get("reasoning_f1", {}).get("status") == "SIGNIFICANTLY_CHANGED"
            and finding_changes.get("reasoning_f1", {}).get(
                "reasoning_vs_normal", {}
            ).get("reasoning_better", False)
        )
        ov3_example_valid = finding_changes.get("overall_f3", {}).get(
            "ov3_example_valid", True
        )

        return {
            "schwartz_hierarchy_reversed": schwartz_reversed,
            "fulva_user_orientation_reversed": fulva_reversed,
            "safety_ceiling_weakened": ceiling_weakened,
            "reasoning_models_now_outperform": reasoning_now_better,
            "ov3_cross_example_still_valid": ov3_example_valid,
            # Summary for prompt rendering
            "any_major_reversal": schwartz_reversed or fulva_reversed,
        }

    # ------------------------------------------------------------------
    # Overall findings
    # ------------------------------------------------------------------

    def _overall_f1_schwartz_order(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        s = a.get("schwartz", {})
        overlap = s.get("pan_cultural_overlap", 4)
        low_ok  = s.get("low_priority_order_holds", True)

        if overlap >= self.SCHWARTZ_TOP4_NEEDED and low_ok:
            # If we have baseline, check whether order has actually shifted at top level
            if old_a:
                old_s = old_a.get("schwartz", {})
                old_top4 = set(old_s.get("dimension_ranking", {}).get("ordered", [])[:4])
                new_top4 = set(s.get("dimension_ranking", {}).get("ordered", [])[:4])
                if old_top4 == new_top4:
                    return {
                        "status": "KEEP",
                        "reason": "Pan-cultural value ordering unchanged vs. baseline.",
                        "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
                        "safety_dim_leaders": s.get("safety_dim_leaders", []),
                    }
            return {
                "status": "KEEP",
                "reason": "Pan-cultural value ordering still holds.",
                "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
                "safety_dim_leaders": s.get("safety_dim_leaders", []),
            }
        elif overlap >= self.SCHWARTZ_TOP4_NEEDED:
            return {
                "status": "ADAPT",
                "reason": "Top-4 intact but bottom-3 ordering shifted.",
                "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
            }
        else:
            return {
                "status": "SIGNIFICANTLY_CHANGED",
                "reason": f"Only {overlap}/4 expected top dims still in top-4; ordering may have reversed.",
                "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
            }

    def _overall_f2_western_bias(self) -> Dict[str, Any]:
        """Overall F2 always FREEZE: country similarity matrix not in Excel."""
        return {
            "status": "FREEZE",
            "reason": (
                "Country-level Schwartz similarity matrix is not present in the "
                "benchmark Excel.  All L2 sentences are frozen.  L1 explanatory "
                "sentences (Western corpus dominance, translated data, etc.) are "
                "kept verbatim.  Append the [DATA PENDING] footnote."
            ),
            "data_pending_footnote": (
                "[DATA PENDING] The core data for this finding (model-vs-country "
                "Schwartz similarity matrix) is absent from the current dataset. "
                "Content preserved from the previous human report. "
                "Theoretical background: Kirk et al. (2024) PRISM, arXiv:2404.16019."
            ),
        }

    def _overall_f3_cross_framework(self, a: Dict) -> Dict[str, Any]:
        s = a.get("schwartz", {})
        leaders = s.get("dimension_leaders", {})
        m = a.get("mft", {})

        # Check whether the OV-3 canonical cross-framework example still holds
        cf = a.get("cross_framework", {})
        ov3_ex = cf.get("ov3_o3mini_example", {})
        ov3_valid = ov3_ex.get("still_valid", True)  # default True if data missing

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Model examples and dimension scores must reflect current data.",
            "self_direction_leader": leaders.get("Self-direction", {}).get("model") if isinstance(leaders.get("Self-direction"), dict) else leaders.get("Self-direction"),
            "conformity_leader":     leaders.get("Conformity", {}).get("model") if isinstance(leaders.get("Conformity"), dict) else leaders.get("Conformity"),
            "stimulation_leader":    leaders.get("Stimulation", {}).get("model") if isinstance(leaders.get("Stimulation"), dict) else leaders.get("Stimulation"),
            "mft_best_model":        m.get("best_model"),
            "mft_hardest_dims":      m.get("hardest_dimensions", []),
            "ov3_example_valid":     ov3_valid,
            "ov3_example_detail":    ov3_ex,
        }

    def _overall_f4_static_ceiling(self, a: Dict) -> Dict[str, Any]:
        r = a.get("risk", {})
        m = a.get("mft", {})
        ceiling = r.get("ceiling_effect", True)
        best_mft = m.get("best_model")
        best_evr = m.get("best_evr_avg")

        if ceiling:
            return {
                "status": "REFRESH_EXAMPLES",
                "reason": "Ceiling effect still holds; update model name examples.",
                "top_safety_models":  r.get("top_safety_models", []),
                "best_mft_model":     best_mft,
                "best_evr_avg":       best_evr,
            }
        return {
            "status": "SIGNIFICANTLY_CHANGED",
            "reason": "Safety ceiling effect weakening — fewer models above 90.",
            "pct_above_90": r.get("pct_models_above_90_safety"),
        }

    # ------------------------------------------------------------------
    # Schwartz findings
    # ------------------------------------------------------------------

    def _schwartz_f1_pan_cultural(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        s = a.get("schwartz", {})
        overlap = s.get("pan_cultural_overlap", 4)
        leaders = s.get("dimension_leaders", {})

        if overlap < self.SCHWARTZ_TOP4_NEEDED:
            return {
                "status": "SIGNIFICANTLY_CHANGED",
                "reason": "Pan-cultural top-4 ordering has shifted substantially.",
                "dimension_leaders": leaders,
            }

        # With baseline: check if key dimension leaders actually changed with meaningful margin
        if old_a:
            old_s = old_a.get("schwartz", {})
            old_leaders = old_s.get("dimension_leaders", {})
            key_dims = ["Self-direction", "Conformity", "Universalism", "Stimulation"]

            any_meaningful_change = False
            n_leaders_changed = 0
            max_leader_margin = 0.0
            for dim in key_dims:
                new_info = leaders.get(dim, {})
                old_info = old_leaders.get(dim, {})

                new_model = new_info.get("model") if isinstance(new_info, dict) else new_info
                old_model = old_info.get("model") if isinstance(old_info, dict) else old_info
                margin = new_info.get("margin") if isinstance(new_info, dict) else None
                if margin is not None and margin > max_leader_margin:
                    max_leader_margin = margin

                if old_model and new_model and old_model != new_model:
                    # Only flag change if the new leader's margin >= MIN_LEADERSHIP_MARGIN
                    if margin is not None and margin >= self.MIN_LEADERSHIP_MARGIN:
                        any_meaningful_change = True
                        n_leaders_changed += 1
                    elif margin is None:
                        # No margin data — conservatively treat as changed
                        any_meaningful_change = True
                        n_leaders_changed += 1

            if not any_meaningful_change:
                return {
                    "status": "KEEP",
                    "reason": "Pan-cultural trend holds; dimension leaders stable vs. baseline.",
                    "dimension_leaders": leaders,
                    "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
                }

            # Build a qualifier note so the writer knows to update the title's scale word
            title_qualifier_note = None
            if n_leaders_changed >= 2 or max_leader_margin > 0.1:
                title_qualifier_note = (
                    f"{n_leaders_changed}/{len(key_dims)} key dimension leaders have changed "
                    f"(largest margin={max_leader_margin:.3f}). "
                    f"The Tier A title qualifier 'subtle preference differences' may "
                    f"understate the actual variation. "
                    f"If the new body examples show leaders with large margins, "
                    f"replace 'subtle' with 'notable' in the title sentence."
                )

            return {
                "status": "REFRESH_EXAMPLES",
                "reason": "Pan-cultural trend holds; update per-model dimension leaders.",
                "dimension_leaders": leaders,
                "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
                "n_leaders_changed": n_leaders_changed,
                "max_leader_margin": round(max_leader_margin, 3),
                "title_qualifier_note": title_qualifier_note,
            }

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Pan-cultural trend holds; update per-model dimension leaders.",
            "dimension_leaders": leaders,
            "dimension_order": s.get("dimension_ranking", {}).get("ordered", []),
        }

    def _schwartz_f2_pronounced(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        s = a.get("schwartz", {})
        top3 = [m["model"] for m in s.get("model_total_ranking", [])[:3]]

        if old_a:
            old_s = old_a.get("schwartz", {})
            old_top3_entries = old_s.get("model_total_ranking", [])[:3]
            old_top3_set = {m["model"] for m in old_top3_entries}
            new_top3_set = set(top3)

            if old_top3_set == new_top3_set:
                # Same models in top-3; also check score changes are meaningful
                old_scores = {m["model"]: m.get("value", 0) for m in old_top3_entries}
                new_entries = s.get("model_total_ranking", [])[:3]
                new_scores = {m["model"]: m.get("value", 0) for m in new_entries}
                max_delta = max(
                    abs(new_scores.get(m, 0) - old_scores.get(m, 0))
                    for m in new_top3_set
                ) if new_top3_set else 0
                if max_delta < 0.05:
                    return {
                        "status": "KEEP",
                        "reason": "Top-3 model set and scores unchanged vs. baseline.",
                        "top3_models": top3,
                        "full_ranking": s.get("model_total_ranking", []),
                    }

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Top models by total Schwartz score need updating.",
            "top3_models": top3,
            "full_ranking": s.get("model_total_ranking", []),
        }

    # ------------------------------------------------------------------
    # MFT findings
    # ------------------------------------------------------------------

    def _mft_f1_aligned_outperform(self, a: Dict) -> Dict[str, Any]:
        m = a.get("mft", {})
        best    = m.get("best_model")
        gap     = m.get("top_runner_up_gap", 0.0) or 0.0
        large   = m.get("large_gap", False)

        if large:
            return {
                "status": "REFRESH_EXAMPLES",
                "reason": f"Best model ({best}) still dominates with gap={gap:.1f} pp; update name.",
                "best_model": best,
                "best_evr_avg": m.get("best_evr_avg"),
                "top_ranking": m.get("model_ranking_by_evr_avg", []),
            }
        return {
            "status": "ADAPT",
            "reason": f"Best model ({best}) leads by only {gap:.1f} pp; dominance less clear.",
            "best_model": best,
            "best_evr_avg": m.get("best_evr_avg"),
        }

    def _mft_f2_dim_variation(self, a: Dict) -> Dict[str, Any]:
        m = a.get("mft", {})
        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Dimension weakness per model/family must be updated from new data.",
            "hardest_dimensions": m.get("hardest_dimensions", []),
            "easiest_dimensions": m.get("easiest_dimensions", []),
            "model_weak_dims":    m.get("model_weak_dimensions", {}),
            "dim_evr_means":      m.get("dimension_evr_means", {}),
        }

    # ------------------------------------------------------------------
    # Safety findings
    # ------------------------------------------------------------------

    def _safety_f1_ceiling(self, a: Dict) -> Dict[str, Any]:
        r = a.get("risk", {})
        pct  = r.get("pct_models_above_90_safety", 0.0) or 0.0
        ceil = r.get("ceiling_effect", False)

        if ceil:
            return {
                "status": "KEEP",
                "reason": f"{pct:.0f}% of models still above 90 safety — ceiling effect persists.",
                "top_safety_models": r.get("top_safety_models", []),
            }
        return {
            "status": "ADAPT",
            "reason": f"Only {pct:.0f}% above 90; ceiling effect may be weakening.",
            "top_safety_models": r.get("top_safety_models", []),
        }

    def _safety_f2_categories(self, a: Dict) -> Dict[str, Any]:
        r = a.get("risk", {})
        hardest = r.get("hardest_categories", [])
        easiest = r.get("easiest_categories", [])

        rep_tox_hard = any("rep" in c.lower() or "tox" in c.lower() for c in hardest)
        misinfo_hard = any("mis" in c.lower() for c in hardest)

        if rep_tox_hard and misinfo_hard:
            return {
                "status": "KEEP",
                "reason": "Rep_Toxicity and Misinfo still the hardest categories.",
                "hardest_categories": hardest,
                "easiest_categories": easiest,
                "category_ranking":   r.get("category_ranking", {}),
            }
        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Category difficulty ordering has changed — update names.",
            "hardest_categories": hardest,
            "easiest_categories": easiest,
            "category_ranking":   r.get("category_ranking", {}),
        }

    # ------------------------------------------------------------------
    # FULVA findings
    # ------------------------------------------------------------------

    # Family findings
    # ------------------------------------------------------------------

    _MAJOR_FAMILIES = {"openai", "anthropic", "google", "meta", "microsoft",
                       "gpt", "claude", "gemini", "llama", "phi"}

    def _families_f1_consistency(self, a: Dict) -> Dict[str, Any]:
        """
        Check intra-family Schwartz consistency from current data.
        Returns SIGNIFICANTLY_CHANGED if a major family diverges (spread > 0.20).
        Returns REFRESH_EXAMPLES with validated consistent_families list otherwise.
        """
        cs = a.get("cross_section", {})
        consistent   = cs.get("consistent_families", [])
        diverging    = cs.get("diverging_families", [])
        consistency  = cs.get("family_consistency", {})

        # Check if any major family is in the diverging list
        major_diverging = [
            f for f in diverging
            if any(m in f.lower() for m in self._MAJOR_FAMILIES)
        ]

        if major_diverging:
            details = "; ".join(
                f"{f} (max_spread={consistency.get(f, {}).get('max_spread', '?')})"
                for f in major_diverging
            )
            return {
                "status": "SIGNIFICANTLY_CHANGED",
                "reason": (
                    f"Major family divergence detected: {details}. "
                    "Intra-family spread exceeds 0.20 — delete condition triggered. "
                    "Do NOT claim these families show consistent patterns."
                ),
                "major_diverging_families": major_diverging,
                "consistent_families": consistent,
            }

        if not consistent and not consistency:
            # No family data available — fall back to refresh
            return {
                "status": "REFRESH_EXAMPLES",
                "reason": "Family consistency data unavailable; update examples from current model list.",
            }

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": (
                f"Intra-family consistency validated. "
                f"Consistent families (spread ≤ 0.15): {consistent or 'none verified'}. "
                f"Use ONLY these families as positive consistency examples."
            ),
            "consistent_families": consistent,
            "diverging_families":  diverging,
        }

    # FULVA findings
    # ------------------------------------------------------------------

    def _fulva_f1_user_bias(self, a: Dict) -> Dict[str, Any]:
        f = a.get("fulva", {})
        holds  = f.get("user_oriented_bias_holds", True)
        pairs  = f.get("pair_comparisons", [])
        n_ok   = f.get("n_pairs_direction_correct", len(pairs))

        # --- Dual-threshold check for Ethical vs Professional ---
        # Direction alone is insufficient: gap must be > 0.05 AND
        # > 65% of models must show Ethical > Professional individually.
        eth_pro_weak = False
        eth_pro_note = ""
        for p in pairs:
            if "Ethical" in p.get("pair", "") and "Professional" in p.get("pair", ""):
                gap      = p.get("gap", 1.0)
                n_pos    = p.get("models_with_positive_gap", 0)
                n_total  = p.get("total_models", 1)
                pct_pos  = n_pos / n_total if n_total > 0 else 0.0
                if gap <= 0.05 or pct_pos <= 0.65:
                    eth_pro_weak = True
                    eth_pro_note = (
                        f"Ethical-Professional gap={gap:.3f} (threshold >0.05), "
                        f"{n_pos}/{n_total} models positive ({pct_pos:.0%}, threshold >65%). "
                        "Claim 'Ethical over Professional is a consistent trend' is NOT supported — "
                        "weaken or remove this sub-clause."
                    )
                break

        if holds and not eth_pro_weak:
            return {
                "status": "KEEP",
                "reason": "User-oriented bias direction holds for all three pairs with sufficient magnitude.",
                "pair_comparisons": pairs,
            }

        if eth_pro_weak and holds:
            # Other pairs OK but Ethical/Professional is too weak to claim as consistent
            return {
                "status": "ADAPT",
                "reason": eth_pro_note,
                "pair_comparisons": pairs,
                "weaken_ethical_professional": True,
            }

        return {
            "status": "ADAPT" if n_ok > 0 else "SIGNIFICANTLY_CHANGED",
            "reason": (
                f"Only {n_ok}/{len(pairs)} pairs show expected direction."
                + (f" Also: {eth_pro_note}" if eth_pro_weak else "")
            ),
            "pair_comparisons": pairs,
            "failed_pairs": [p["pair"] for p in pairs if not p.get("direction_holds")],
            **({"weaken_ethical_professional": True} if eth_pro_weak else {}),
        }

    def _fulva_f2_top_models(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        f = a.get("fulva", {})
        ranking = f.get("model_ranking", [])
        top2 = [m["model"] for m in ranking[:2]]

        if old_a:
            old_f = old_a.get("fulva", {})
            old_top2 = {m["model"] for m in old_f.get("model_ranking", [])[:2]}
            if set(top2) == old_top2:
                return {
                    "status": "KEEP",
                    "reason": "Top-2 FULVA models unchanged vs. baseline.",
                    "top2_models": top2,
                    "full_ranking": ranking,
                }

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Top FULVA models must always be updated from new data.",
            "top2_models":   top2,
            "full_ranking":  ranking,
        }

    # ------------------------------------------------------------------
    # Proprietary vs. Open findings
    # ------------------------------------------------------------------

    def _prop_f1_mft_gap(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        m = a.get("mft", {})
        evr_by_type = m.get("evr_by_type", {})

        if not evr_by_type:
            return {
                "status": "KEEP",
                "reason": "No model-type breakdown in MFT data; preserve existing text.",
            }

        close_key = next((k for k in evr_by_type if "close" in k.lower() or "prop" in k.lower()), None)
        open_key  = next((k for k in evr_by_type if "open" in k.lower()), None)

        if close_key and open_key:
            close_evr = evr_by_type[close_key]
            open_evr  = evr_by_type[open_key]
            gap = open_evr - close_evr  # positive = proprietary better (lower EVR)

            # Determine intensity from intensity_metrics if available
            intensity_metrics = a.get("intensity_metrics", {})
            intensity_word = intensity_metrics.get("prop_vs_open_intensity", "")

            if gap > self.MFT_TYPE_GAP_PP:
                return {
                    "status": "KEEP",
                    "reason": f"Proprietary advantage on MFT still clear (gap={gap:.1f} pp).",
                    "evr_by_type": evr_by_type,
                    "intensity_word": intensity_word,
                }
            # Gap narrowed — check if intensity changed
            if old_a:
                old_m = old_a.get("mft", {})
                old_evr_by_type = old_m.get("evr_by_type", {})
                old_ck = next((k for k in old_evr_by_type if "close" in k.lower() or "prop" in k.lower()), None)
                old_ok = next((k for k in old_evr_by_type if "open" in k.lower()), None)
                if old_ck and old_ok:
                    old_gap = old_evr_by_type[old_ok] - old_evr_by_type[old_ck]
                    if abs(gap - old_gap) < 2.0:  # minimal change
                        return {
                            "status": "KEEP",
                            "reason": f"MFT gap proprietary/open minimally changed ({old_gap:.1f} -> {gap:.1f} pp).",
                            "evr_by_type": evr_by_type,
                            "intensity_word": intensity_word,
                        }
            return {
                "status": "ADAPT",
                "reason": f"MFT gap proprietary/open narrowed to {gap:.1f} pp.",
                "evr_by_type": evr_by_type,
                "intensity_word": intensity_word,
            }

        return {"status": "KEEP", "reason": "Cannot identify open/close keys; preserve text."}

    def _prop_f2_schwartz_gap(self, a: Dict) -> Dict[str, Any]:
        cs = a.get("cross_section", {})
        by_type = cs.get("schwartz_by_type", {})
        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Open-source model examples must be verified with current data.",
            "schwartz_by_type": by_type,
        }

    # ------------------------------------------------------------------
    # Reasoning findings
    # ------------------------------------------------------------------

    def _reasoning_f1_safety(
        self, a: Dict, old_a: Optional[Dict] = None
    ) -> Dict[str, Any]:
        m = a.get("mft", {})
        r_vs_n = m.get("reasoning_vs_normal_evr", {})
        intensity_metrics = a.get("intensity_metrics", {})

        if r_vs_n:
            r_better = r_vs_n.get("reasoning_better", False)
            intensity = intensity_metrics.get("reasoning_mft_intensity", "")
            if not r_better:
                return {
                    "status": "REFRESH_EXAMPLES",
                    "reason": "Reasoning models still don't consistently outperform; update examples.",
                    "reasoning_vs_normal": r_vs_n,
                    "intensity_word": intensity,
                }
            # Reasoning models now better — is this a reversal from baseline?
            if old_a:
                old_m = old_a.get("mft", {})
                old_r_vs_n = old_m.get("reasoning_vs_normal_evr", {})
                old_r_better = old_r_vs_n.get("reasoning_better", False) if old_r_vs_n else False
                if not old_r_better:
                    return {
                        "status": "SIGNIFICANTLY_CHANGED",
                        "reason": "Reasoning models NOW outperform normal models on MFT — reversal detected.",
                        "reasoning_vs_normal": r_vs_n,
                        "intensity_word": intensity,
                    }
            return {
                "status": "REFRESH_EXAMPLES",
                "reason": "Reasoning models outperform; update examples.",
                "reasoning_vs_normal": r_vs_n,
                "intensity_word": intensity,
            }

        return {
            "status": "REFRESH_EXAMPLES",
            "reason": "Reasoning vs. normal MFT examples need updating from current data.",
        }

    def _reasoning_f2_schwartz(self, a: Dict) -> Dict[str, Any]:
        cs = a.get("cross_section", {})
        r_vs_n = cs.get("schwartz_reasoning_vs_normal", {})

        if r_vs_n:
            stronger = r_vs_n.get("reasoning_stronger", False)
            if stronger:
                return {
                    "status": "KEEP",
                    "reason": "Reasoning models still show stronger Schwartz value expression.",
                    "reasoning_vs_normal": r_vs_n,
                }
            return {
                "status": "ADAPT",
                "reason": "Reasoning advantage on Schwartz total score has weakened or reversed.",
                "reasoning_vs_normal": r_vs_n,
            }

        return {"status": "KEEP", "reason": "No cross-section Schwartz data for comparison."}
