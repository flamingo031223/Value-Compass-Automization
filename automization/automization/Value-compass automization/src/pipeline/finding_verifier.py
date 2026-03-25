"""
Finding-specific verification engine.

Implements the exact verification code from pipeline_guidance_for_claude_code.md
for all 19 findings. Given the analytics dict from compute_all_analytics(), produces
a VerificationResult per finding that includes:
  - status: KEEP | REPLACE_MODEL | REPLACE_SCORE | MODIFY | REWRITE | FREEZE | DELETE
  - replacements: list of {old, new, context} dicts for exact model-name swaps
  - key_facts: computed values driving the decision (for prompt inclusion)
  - phantom_models: baseline model names that do NOT exist in new data (must not appear in output)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
import re


# ---------------------------------------------------------------------------
# Baseline constants (from leaderboard_results_latest.xlsx, i.e. the human report)
# These are the model names used in the original human-authored report.
# Any of these NOT present in new data are "phantom models" and must not appear.
# ---------------------------------------------------------------------------

BASELINE_MODELS: Set[str] = {
    "o3-mini", "GPT-4o", "GPT-4o-mini", "GPT-4-Turbo",
    "Claude-3.5-Sonnet", "Claude-3.5-Haiku", "Claude-3-Opus",
    "DeepSeek-R1", "DeepSeek-V3",
    "Qwen-Max", "Qwen2.5-72B-Instruct",
    "Gemini-2.0-Flash", "Gemini-1.5-Pro", "Gemini-1.5-Flash",
    "LLaMA-3.1-8B-Instruct", "LLaMA-3.1-70B-Instruct",
    "Phi-3.5-mini-Instruct", "Phi-3-Medium",
    "Mistral-Large", "Mistral-7B-Instruct",
    "o1-mini", "o1",
}

# Finding-specific baseline model name references (from the human report sentences)
BASELINE_REFS = {
    # Overall F1
    "ov_f1_well_aligned_model": "Claude-3.5-Sonnet",
    # Overall F3
    "ov_f3_positive_example": "o3-mini",
    "ov_f3_conformity_example": "DeepSeek-R1",
    # Overall F4
    "ov_f4_mft_best": "Claude-3.5-Sonnet",
    "ov_f4_small_safety_example": "Phi-3-Medium",
    # Schwartz F1
    "sch_f1_selfdirection_leader": "o3-mini",
    "sch_f1_stimulation_leader": "o3-mini",
    "sch_f1_universalism_leader": "Qwen-Max",
    "sch_f1_conformity_leader": "DeepSeek-V3",
    # Schwartz F2
    "sch_f2_top3": ["o3-mini", "Qwen-Max", "Claude-3.5-Sonnet"],
    # MFT F1
    "mft_f1_best_model": "Claude-3.5-Sonnet",
    # MFT F2
    "mft_f2_gemini_example": "Gemini-2.0-Flash",
    # Safety F2
    "safety_f2_hardest_1": "Rep_Toxicity",
    "safety_f2_hardest_2": "Misinfo",
    "safety_f2_easiest_1": "Human_Autonomy",
    "safety_f2_easiest_2": "Info_Safety",
    # FULVA F2
    "fulva_f2_top2": ["DeepSeek-R1", "o1-mini"],
    # Prop F2
    "prop_f2_low_open": ["LLaMA-3.1-8B-Instruct", "Phi-3.5-mini-Instruct"],
    # Families F1
    "families_f1_examples": ["GPT-4o", "GPT-4o-mini", "Claude-3.5-Sonnet", "Claude-3.5-Haiku"],
    # Families F2
    "families_f2_outlier": "o3-mini",
    # Reasoning F1
    "reasoning_f1_best_non_reasoning": "Claude-3.5-Sonnet",
    # Reasoning F2
    "reasoning_f2_pairs": [("o3-mini", "GPT-4o"), ("DeepSeek-R1", "DeepSeek-V3")],
}


# ---------------------------------------------------------------------------
# Main verifier class
# ---------------------------------------------------------------------------

class FindingVerifier:
    """
    Runs exact per-finding verification from new analytics.
    Returns a dict mapping finding_id -> VerificationResult.
    """

    def verify_all(
        self,
        analytics: Dict[str, Any],
        new_model_set: Set[str],
        model_info_df=None,
    ) -> Dict[str, Any]:
        """
        Main entry point. Returns dict: finding_id -> result dict.
        Each result has: status, replacements, key_facts, phantom_models, notes
        """
        # Compute phantom models: baseline references not in new data
        all_phantom = BASELINE_MODELS - new_model_set

        results: Dict[str, Any] = {}

        # --- Overall findings ---
        results["overall_f1"] = self._verify_overall_f1(analytics, new_model_set, all_phantom)
        results["overall_f2"] = self._verify_overall_f2()  # always FREEZE
        results["overall_f3"] = self._verify_overall_f3(analytics, new_model_set, all_phantom)
        results["overall_f4"] = self._verify_overall_f4(analytics, new_model_set, all_phantom)
        results["overall_f5"] = {"status": "KEEP", "replacements": [], "key_facts": {}, "notes": "Methodological critique — no data trigger."}

        # --- Schwartz ---
        results["schwartz_f1"] = self._verify_schwartz_f1(analytics, new_model_set, all_phantom)
        results["schwartz_f2"] = self._verify_schwartz_f2(analytics, new_model_set, all_phantom)

        # --- MFT ---
        results["mft_f1"] = self._verify_mft_f1(analytics, new_model_set, all_phantom)
        results["mft_f2"] = self._verify_mft_f2(analytics, new_model_set, all_phantom)

        # --- Safety ---
        results["safety_f1"] = self._verify_safety_f1(analytics, new_model_set, all_phantom)
        results["safety_f2"] = self._verify_safety_f2(analytics, new_model_set, all_phantom)

        # --- FULVA ---
        results["fulva_f1"] = self._verify_fulva_f1(analytics, new_model_set, all_phantom)
        results["fulva_f2"] = self._verify_fulva_f2(analytics, new_model_set, all_phantom)

        # --- Proprietary vs Open ---
        results["propclosed_f1"] = self._verify_prop_f1(analytics, new_model_set, all_phantom)
        results["propclosed_f2"] = self._verify_prop_f2(analytics, new_model_set, all_phantom)

        # --- Families ---
        results["families_f1"] = self._verify_families_f1(analytics, new_model_set, all_phantom)
        results["families_f2"] = self._verify_families_f2(analytics, new_model_set, all_phantom)

        # --- Reasoning ---
        results["reasoning_f1"] = self._verify_reasoning_f1(analytics, new_model_set, all_phantom)
        results["reasoning_f2"] = self._verify_reasoning_f2(analytics, new_model_set, all_phantom)

        return results

    def _phantom(self, models: Set[str], new_set: Set[str]) -> List[str]:
        """Return models NOT in new_set."""
        return sorted(m for m in models if m not in new_set)

    def _get_model(self, ranking: List[Dict], idx: int = 0) -> Optional[str]:
        if ranking and idx < len(ranking):
            return ranking[idx].get("model")
        return None

    # ------------------------------------------------------------------
    # Overall F1: LLMs broadly aligned with human values (Schwartz top-4)
    # ------------------------------------------------------------------
    def _verify_overall_f1(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        ordered = s.get("dimension_ranking", {}).get("ordered", [])
        top4 = set(ordered[:4]) if len(ordered) >= 4 else set()
        expected_top4 = {"Universalism", "Benevolence", "Security", "Self-direction"}
        overlap = len(expected_top4 & top4)

        # Well-aligned model: high on Universalism + Benevolence + Security
        safety_leaders = s.get("safety_dim_leaders", [])
        new_well_aligned = self._get_model(safety_leaders)

        baseline_well_aligned = BASELINE_REFS["ov_f1_well_aligned_model"]
        replacements = []
        if new_well_aligned and new_well_aligned != baseline_well_aligned:
            replacements.append({
                "old": baseline_well_aligned,
                "new": new_well_aligned,
                "context": "well-aligned model (high on Universalism/Benevolence/Security)",
            })
        elif baseline_well_aligned in phantom:
            # baseline model not in new data, must replace with best available
            replacements.append({
                "old": baseline_well_aligned,
                "new": new_well_aligned or "[check data]",
                "context": "well-aligned model not in new data",
            })

        if overlap >= 3:
            status = "KEEP" if not replacements else "REPLACE_MODEL"
        else:
            status = "REWRITE"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "dimension_order": ordered,
                "top4_overlap_with_expected": overlap,
                "well_aligned_model": new_well_aligned,
            },
            "phantom_models": self._phantom({baseline_well_aligned}, new_set),
            "notes": f"Top-4 overlap with expected: {overlap}/4",
        }

    # ------------------------------------------------------------------
    # Overall F2: Western bias — FREEZE (country matrix not in Excel)
    # ------------------------------------------------------------------
    def _verify_overall_f2(self):
        return {
            "status": "FREEZE",
            "replacements": [],
            "key_facts": {},
            "phantom_models": [],
            "notes": (
                "Country-level Schwartz similarity matrix absent from Excel. "
                "Preserve entire finding verbatim. Append [DATA PENDING] footnote. "
                "Baseline model names in this finding (e.g. DeepSeek-R1, Qwen-Max) "
                "come from country-similarity data, NOT Schwartz rankings — keep them."
            ),
        }

    # ------------------------------------------------------------------
    # Overall F3: Value belief vs behavior consistency
    # ------------------------------------------------------------------
    def _verify_overall_f3(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        leaders = s.get("dimension_leaders", {})

        def _leader_model(dim):
            info = leaders.get(dim)
            if isinstance(info, dict):
                return info.get("model")
            return info

        sd_top = _leader_model("Self-direction")
        stim_top = _leader_model("Stimulation")
        conf_top = _leader_model("Conformity")
        baseline_positive = BASELINE_REFS["ov_f3_positive_example"]  # o3-mini
        baseline_conf = BASELINE_REFS["ov_f3_conformity_example"]    # DeepSeek-R1

        replacements = []
        # Positive example (high Self-direction AND Stimulation)
        new_positive = sd_top if sd_top == stim_top else sd_top  # prefer model leading both
        if new_positive and new_positive != baseline_positive:
            replacements.append({
                "old": baseline_positive,
                "new": new_positive,
                "context": "example model with high Self-direction and Stimulation",
            })
        elif baseline_positive in phantom:
            replacements.append({
                "old": baseline_positive,
                "new": new_positive or "[data-driven model]",
                "context": "o3-mini not in new data",
            })

        if conf_top and conf_top != baseline_conf:
            replacements.append({
                "old": baseline_conf,
                "new": conf_top,
                "context": "Conformity leader example",
            })
        elif baseline_conf in phantom:
            replacements.append({
                "old": baseline_conf,
                "new": conf_top or "[data-driven model]",
                "context": "DeepSeek-R1 not in new data",
            })

        status = "KEEP" if not replacements else "REPLACE_MODEL"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "selfdirection_leader": sd_top,
                "stimulation_leader": stim_top,
                "conformity_leader": conf_top,
            },
            "phantom_models": self._phantom({baseline_positive, baseline_conf}, new_set),
        }

    # ------------------------------------------------------------------
    # Overall F4: Safety benchmarks may overestimate safety (ceiling effect)
    # ------------------------------------------------------------------
    def _verify_overall_f4(self, a, new_set, phantom):
        r = a.get("risk", {})
        m = a.get("mft", {})

        pct_above_90 = r.get("pct_models_above_90_safety", 0)
        ceiling = r.get("ceiling_effect", False)
        top_safety = r.get("top_safety_models", [])
        best_mft = m.get("best_model")

        baseline_mft = BASELINE_REFS["ov_f4_mft_best"]  # Claude-3.5-Sonnet
        baseline_small = BASELINE_REFS["ov_f4_small_safety_example"]  # Phi-3-Medium

        replacements = []
        if best_mft and best_mft != baseline_mft:
            replacements.append({
                "old": baseline_mft,
                "new": best_mft,
                "context": "MFT best model (lowest EVR avg)",
            })
        elif baseline_mft in phantom:
            replacements.append({
                "old": baseline_mft,
                "new": best_mft or "[check MFT data]",
                "context": "baseline MFT best model not in new data",
            })

        # Small model safety example
        if baseline_small in phantom and top_safety:
            new_example = self._get_model(top_safety)
            if new_example:
                replacements.append({
                    "old": baseline_small,
                    "new": new_example,
                    "context": "small model with high safety score example",
                })

        status = "REPLACE_MODEL" if replacements else "KEEP"
        if not ceiling:
            status = "MODIFY"  # ceiling effect weakened

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "pct_above_90": pct_above_90,
                "ceiling_effect": ceiling,
                "best_mft_model": best_mft,
                "top_safety_models": [e.get("model") for e in top_safety[:3]],
            },
            "phantom_models": self._phantom({baseline_mft, baseline_small}, new_set),
        }

    # ------------------------------------------------------------------
    # Schwartz F1: Pan-cultural value order
    # ------------------------------------------------------------------
    def _verify_schwartz_f1(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        leaders = s.get("dimension_leaders", {})

        def _leader_model(dim):
            info = leaders.get(dim)
            return info.get("model") if isinstance(info, dict) else info

        def _leader_margin(dim):
            info = leaders.get(dim)
            return info.get("margin") if isinstance(info, dict) else None

        sd_top = _leader_model("Self-direction")
        stim_top = _leader_model("Stimulation")
        univ_top = _leader_model("Universalism")
        conf_top = _leader_model("Conformity")

        baseline_sd = BASELINE_REFS["sch_f1_selfdirection_leader"]    # o3-mini
        baseline_stim = BASELINE_REFS["sch_f1_stimulation_leader"]    # o3-mini
        baseline_univ = BASELINE_REFS["sch_f1_universalism_leader"]   # Qwen-Max
        baseline_conf = BASELINE_REFS["sch_f1_conformity_leader"]     # DeepSeek-V3

        replacements = []
        MIN_MARGIN = 0.05

        for dim, new_leader, baseline in [
            ("Self-direction", sd_top, baseline_sd),
            ("Stimulation", stim_top, baseline_stim),
            ("Universalism", univ_top, baseline_univ),
            ("Conformity", conf_top, baseline_conf),
        ]:
            if new_leader is None:
                continue
            margin = _leader_margin(dim) or 0
            if new_leader != baseline and margin >= MIN_MARGIN:
                replacements.append({
                    "old": baseline,
                    "new": new_leader,
                    "context": f"{dim} leader (margin={margin:.3f})",
                })
            elif baseline in phantom:
                replacements.append({
                    "old": baseline,
                    "new": new_leader,
                    "context": f"{baseline} not in new data; {dim} leader now {new_leader}",
                })

        ordered = s.get("dimension_ranking", {}).get("ordered", [])
        expected_top4 = {"Universalism", "Benevolence", "Security", "Self-direction"}
        top4 = set(ordered[:4]) if len(ordered) >= 4 else set()
        overlap = len(expected_top4 & top4)

        if overlap < 3:
            status = "REWRITE"
        elif replacements:
            status = "REPLACE_MODEL"
        else:
            status = "KEEP"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "dimension_order": ordered,
                "top4_overlap": overlap,
                "Self-direction_leader": sd_top,
                "Stimulation_leader": stim_top,
                "Universalism_leader": univ_top,
                "Conformity_leader": conf_top,
            },
            "phantom_models": self._phantom(
                {baseline_sd, baseline_stim, baseline_univ, baseline_conf}, new_set
            ),
        }

    # ------------------------------------------------------------------
    # Schwartz F2: Models with pronounced value orientations
    # ------------------------------------------------------------------
    def _verify_schwartz_f2(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        ranking = s.get("model_total_ranking", [])
        new_top3 = [self._get_model(ranking, i) for i in range(3)]
        new_top3 = [m for m in new_top3 if m]

        baseline_top3 = BASELINE_REFS["sch_f2_top3"]  # ["o3-mini", "Qwen-Max", "Claude-3.5-Sonnet"]

        replacements = []
        for i, (old, new) in enumerate(zip(baseline_top3, new_top3)):
            if old != new:
                replacements.append({
                    "old": old,
                    "new": new,
                    "context": f"Schwartz total score rank #{i+1}",
                })
        # Handle if phantom models in baseline_top3
        for old in baseline_top3:
            if old in phantom and not any(r["old"] == old for r in replacements):
                # find replacement
                idx = baseline_top3.index(old)
                new_m = new_top3[idx] if idx < len(new_top3) else None
                if new_m:
                    replacements.append({
                        "old": old,
                        "new": new_m,
                        "context": f"{old} not in new data; new rank-{idx+1} is {new_m}",
                    })

        status = "REPLACE_MODEL" if replacements else "KEEP"

        # Check if ranking is flat (no pronounced orientation pattern)
        scores = [e.get("value", 0) for e in ranking]
        spread = (max(scores) - min(scores)) if len(scores) >= 2 else 1.0
        if spread < 0.3:
            status = "REWRITE"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "top3_models": new_top3,
                "full_top5": [(e.get("model"), e.get("value")) for e in ranking[:5]],
                "score_spread": round(spread, 3),
            },
            "phantom_models": self._phantom(set(baseline_top3), new_set),
        }

    # ------------------------------------------------------------------
    # MFT F1: Well-aligned LLMs outperform on moral alignment
    # ------------------------------------------------------------------
    def _verify_mft_f1(self, a, new_set, phantom):
        m = a.get("mft", {})
        best = m.get("best_model")
        best_evr = m.get("best_evr_avg")
        gap = m.get("top_runner_up_gap", 0) or 0
        baseline_best = BASELINE_REFS["mft_f1_best_model"]  # Claude-3.5-Sonnet

        replacements = []
        if best and best != baseline_best:
            replacements.append({
                "old": baseline_best,
                "new": best,
                "context": f"MFT best model (lowest EVR avg={best_evr}%)",
            })
        elif baseline_best in phantom:
            replacements.append({
                "old": baseline_best,
                "new": best or "[check MFT data]",
                "context": "baseline MFT best model not in new data",
            })

        status = "REPLACE_MODEL" if replacements else "KEEP"
        if gap < 10:
            # Gap not large enough for "significantly outperforms" claim
            status = "MODIFY" if not replacements else "REPLACE_MODEL"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "best_model": best,
                "best_evr_avg": best_evr,
                "gap_to_runner_up_pp": gap,
                "large_dominance": gap > 10,
                "top5": [(e.get("model"), e.get("value")) for e in m.get("model_ranking_by_evr_avg", [])[:5]],
            },
            "phantom_models": self._phantom({baseline_best}, new_set),
        }

    # ------------------------------------------------------------------
    # MFT F2: Different models struggle with different moral dimensions
    # ------------------------------------------------------------------
    def _verify_mft_f2(self, a, new_set, phantom):
        m = a.get("mft", {})
        weak_dims = m.get("model_weak_dimensions", {})
        dim_means = m.get("dimension_evr_means", {})
        hardest = m.get("hardest_dimensions", [])
        easiest = m.get("easiest_dimensions", [])

        baseline_gemini = BASELINE_REFS["mft_f2_gemini_example"]  # Gemini-2.0-Flash
        replacements = []

        if baseline_gemini in phantom:
            # Find actual Gemini model in new data
            gemini_in_new = [mdl for mdl in new_set if "gemini" in mdl.lower()]
            new_gemini = gemini_in_new[0] if gemini_in_new else None
            if new_gemini:
                replacements.append({
                    "old": baseline_gemini,
                    "new": new_gemini,
                    "context": "Gemini model example for dimension weakness",
                })

        return {
            "status": "REPLACE_MODEL" if replacements else "KEEP",
            "replacements": replacements,
            "key_facts": {
                "hardest_dimensions": hardest,
                "easiest_dimensions": easiest,
                "dim_evr_means": dim_means,
                "model_weak_dims_sample": dict(list(weak_dims.items())[:5]),
            },
            "phantom_models": self._phantom({baseline_gemini}, new_set),
        }

    # ------------------------------------------------------------------
    # Safety F1: Advanced LLMs achieving near-perfect safety
    # ------------------------------------------------------------------
    def _verify_safety_f1(self, a, new_set, phantom):
        r = a.get("risk", {})
        pct = r.get("pct_models_above_90_safety", 0)
        ceiling = r.get("ceiling_effect", False)
        top3 = r.get("top_safety_models", [])

        status = "KEEP" if ceiling else "MODIFY"
        return {
            "status": status,
            "replacements": [],
            "key_facts": {
                "pct_above_90": pct,
                "ceiling_effect": ceiling,
                "top_safety_models": [e.get("model") for e in top3[:3]],
            },
            "phantom_models": [],
            "notes": f"{pct:.0f}% of models above 90 safety score",
        }

    # ------------------------------------------------------------------
    # Safety F2: Different harm categories
    # ------------------------------------------------------------------
    def _verify_safety_f2(self, a, new_set, phantom):
        r = a.get("risk", {})
        hardest = r.get("hardest_categories", [])
        easiest = r.get("easiest_categories", [])
        cat_rank = r.get("category_ranking", {})

        baseline_hard_1 = BASELINE_REFS["safety_f2_hardest_1"]   # Rep_Toxicity
        baseline_hard_2 = BASELINE_REFS["safety_f2_hardest_2"]   # Misinfo
        baseline_easy_1 = BASELINE_REFS["safety_f2_easiest_1"]   # Human_Autonomy
        baseline_easy_2 = BASELINE_REFS["safety_f2_easiest_2"]   # Info_Safety

        replacements = []
        # Check if hardest/easiest categories changed
        new_hard_set = set(hardest[:2])
        new_easy_set = set(easiest[:2])
        baseline_hard_set = {baseline_hard_1, baseline_hard_2}
        baseline_easy_set = {baseline_easy_1, baseline_easy_2}

        if new_hard_set != baseline_hard_set and hardest:
            # Categories changed — need to update all category references
            replacements.append({
                "old": f"{baseline_hard_1} and {baseline_hard_2}",
                "new": f"{hardest[0]} and {hardest[1]}" if len(hardest) >= 2 else hardest[0],
                "context": "hardest safety categories (highest ASR)",
            })

        if new_easy_set != baseline_easy_set and easiest:
            replacements.append({
                "old": f"{baseline_easy_1} and {baseline_easy_2}",
                "new": f"{easiest[0]} and {easiest[1]}" if len(easiest) >= 2 else easiest[0],
                "context": "easiest safety categories (lowest ASR)",
            })

        status = "REPLACE_MODEL" if replacements else "KEEP"

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "hardest_categories": hardest,
                "easiest_categories": easiest,
                "category_ranking": cat_rank,
            },
            "phantom_models": [],
        }

    # ------------------------------------------------------------------
    # FULVA F1: LLMs prefer user-oriented values
    # ------------------------------------------------------------------
    def _verify_fulva_f1(self, a, new_set, phantom):
        f = a.get("fulva", {})
        holds = f.get("user_oriented_bias_holds", True)
        pairs = f.get("pair_comparisons", [])

        status = "KEEP" if holds else ("MODIFY" if any(p.get("direction_holds") for p in pairs) else "REWRITE")
        return {
            "status": status,
            "replacements": [],
            "key_facts": {
                "user_oriented_bias_holds": holds,
                "pair_comparisons": pairs,
            },
            "phantom_models": [],
        }

    # ------------------------------------------------------------------
    # FULVA F2: Top-performing models
    # ------------------------------------------------------------------
    def _verify_fulva_f2(self, a, new_set, phantom):
        f = a.get("fulva", {})
        ranking = f.get("model_ranking", [])
        new_top2 = [self._get_model(ranking, i) for i in range(2)]
        new_top2 = [m for m in new_top2 if m]

        baseline_top2 = BASELINE_REFS["fulva_f2_top2"]  # ["DeepSeek-R1", "o1-mini"]

        replacements = []
        for i, (old, new) in enumerate(zip(baseline_top2, new_top2)):
            if old != new:
                replacements.append({
                    "old": old,
                    "new": new,
                    "context": f"FULVA total score rank #{i+1}",
                })
        for old in baseline_top2:
            if old in phantom and not any(r["old"] == old for r in replacements):
                idx = baseline_top2.index(old)
                new_m = new_top2[idx] if idx < len(new_top2) else None
                if new_m:
                    replacements.append({
                        "old": old,
                        "new": new_m,
                        "context": f"{old} not in new data; replaced by {new_m}",
                    })

        status = "REPLACE_MODEL" if replacements else "KEEP"
        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "top2_models": new_top2,
                "top5": [(e.get("model"), e.get("value")) for e in ranking[:5]],
            },
            "phantom_models": self._phantom(set(baseline_top2), new_set),
        }

    # ------------------------------------------------------------------
    # Prop F1: Alignment training importance
    # ------------------------------------------------------------------
    def _verify_prop_f1(self, a, new_set, phantom):
        m = a.get("mft", {})
        evr_by_type = m.get("evr_by_type", {})
        r = a.get("risk", {})

        close_key = next((k for k in evr_by_type if "close" in k.lower() or "prop" in k.lower()), None)
        open_key = next((k for k in evr_by_type if "open" in k.lower()), None)

        key_facts = {"evr_by_type": evr_by_type}
        if close_key and open_key:
            close_evr = evr_by_type[close_key]
            open_evr = evr_by_type[open_key]
            gap = open_evr - close_evr  # positive = proprietary better
            key_facts["mft_gap_pp"] = round(gap, 2)
            key_facts["gap_direction"] = "proprietary_better" if gap > 0 else "open_better"
            status = "KEEP" if gap > 5 else "MODIFY"
        else:
            status = "KEEP"

        return {
            "status": status,
            "replacements": [],
            "key_facts": key_facts,
            "phantom_models": [],
        }

    # ------------------------------------------------------------------
    # Prop F2: Smaller open-source models weaker on value recognition
    # ------------------------------------------------------------------
    def _verify_prop_f2(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        ranking = s.get("model_total_ranking", [])
        baseline_low = BASELINE_REFS["prop_f2_low_open"]  # ["LLaMA-3.1-8B-Instruct", "Phi-3.5-mini-Instruct"]

        # Find which baseline models are phantom
        phantom_low = [m for m in baseline_low if m in phantom]

        replacements = []
        if phantom_low:
            # Find actual low-scoring open models from new data
            # We need to identify open-source models from the ranking
            # Use heuristic: small models tend to be at the bottom of ranking
            bottom_models = [e.get("model") for e in ranking[-3:] if e.get("model")]
            for i, old in enumerate(phantom_low):
                new_m = bottom_models[i] if i < len(bottom_models) else None
                if new_m:
                    replacements.append({
                        "old": old,
                        "new": new_m,
                        "context": f"low-scoring open-source model example",
                    })

        status = "REPLACE_MODEL" if replacements else "KEEP"
        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "bottom3_models": [(e.get("model"), e.get("value")) for e in ranking[-3:]],
            },
            "phantom_models": self._phantom(set(baseline_low), new_set),
        }

    # ------------------------------------------------------------------
    # Families F1: Models within same family show consistent values
    # ------------------------------------------------------------------
    def _verify_families_f1(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        ranking = s.get("model_total_ranking", [])
        all_models_in_data = {e.get("model") for e in ranking if e.get("model")}

        baseline_examples = BASELINE_REFS["families_f1_examples"]
        phantom_examples = [m for m in baseline_examples if m in phantom]

        # Build family membership from new data (heuristic based on name)
        family_map = {}
        for m in all_models_in_data:
            if "gpt" in m.lower() or "o1" in m.lower() or "o3" in m.lower():
                family_map.setdefault("GPT/OpenAI", []).append(m)
            elif "claude" in m.lower():
                family_map.setdefault("Claude", []).append(m)
            elif "llama" in m.lower():
                family_map.setdefault("LLaMA", []).append(m)
            elif "gemini" in m.lower():
                family_map.setdefault("Gemini", []).append(m)
            elif "phi" in m.lower():
                family_map.setdefault("Phi", []).append(m)
            elif "qwen" in m.lower():
                family_map.setdefault("Qwen", []).append(m)
            elif "deepseek" in m.lower():
                family_map.setdefault("DeepSeek", []).append(m)

        replacements = []
        if phantom_examples:
            for old in phantom_examples:
                # Find a new example from same family
                for fam_models in family_map.values():
                    if old in fam_models:
                        replacements.append({"old": old, "new": fam_models[0] if fam_models else "[check data]", "context": "family consistency example"})
                        break

        return {
            "status": "REPLACE_MODEL" if replacements else "KEEP",
            "replacements": replacements,
            "key_facts": {
                "family_map": {k: v for k, v in family_map.items()},
            },
            "phantom_models": phantom_examples,
            "notes": "Always update family member examples to use models actually in new data.",
        }

    # ------------------------------------------------------------------
    # Families F2: Inter-family > intra-family variation
    # ------------------------------------------------------------------
    def _verify_families_f2(self, a, new_set, phantom):
        s = a.get("schwartz", {})
        ranking = s.get("model_total_ranking", [])
        all_ranked = [(e.get("model"), e.get("value")) for e in ranking if e.get("model")]

        baseline_outlier = BASELINE_REFS["families_f2_outlier"]  # o3-mini
        replacements = []

        # Find actual outlier (highest total score)
        new_outlier = all_ranked[0][0] if all_ranked else None
        if new_outlier and new_outlier != baseline_outlier:
            replacements.append({
                "old": baseline_outlier,
                "new": new_outlier,
                "context": "inter-family outlier (highest Schwartz total)",
            })
        elif baseline_outlier in phantom:
            replacements.append({
                "old": baseline_outlier,
                "new": new_outlier or "[check data]",
                "context": "o3-mini not in new data",
            })

        return {
            "status": "REPLACE_MODEL" if replacements else "KEEP",
            "replacements": replacements,
            "key_facts": {
                "top_model": all_ranked[0] if all_ranked else None,
                "top5": all_ranked[:5],
            },
            "phantom_models": self._phantom({baseline_outlier}, new_set),
        }

    # ------------------------------------------------------------------
    # Reasoning F1: Reasoning models excel at safety
    # ------------------------------------------------------------------
    def _verify_reasoning_f1(self, a, new_set, phantom):
        m = a.get("mft", {})
        best_mft = m.get("best_model")
        ranking = m.get("model_ranking_by_evr_avg", [])

        # Is top MFT model a reasoning model?
        def _is_reasoning(name):
            if not name:
                return False
            n = name.lower()
            return any(k in n for k in ["r1", "o1", "o3", "-r", "thinking", "reason"])

        top_is_reasoning = _is_reasoning(best_mft)
        baseline_best_non_reasoning = BASELINE_REFS["reasoning_f1_best_non_reasoning"]  # Claude-3.5-Sonnet

        replacements = []
        if top_is_reasoning:
            # Reasoning model now leads — this is a REWRITE scenario
            return {
                "status": "REWRITE",
                "replacements": [],
                "key_facts": {
                    "best_mft_model": best_mft,
                    "top_is_reasoning": True,
                    "note": "Reasoning model now leads on MFT — conclusion reversed",
                },
                "phantom_models": self._phantom({baseline_best_non_reasoning}, new_set),
                "notes": "REWRITE: reasoning model now tops MFT ranking; original claim (non-reasoning leads) is reversed.",
            }

        # Non-reasoning still leads
        if best_mft and best_mft != baseline_best_non_reasoning:
            replacements.append({
                "old": baseline_best_non_reasoning,
                "new": best_mft,
                "context": "best MFT model (still non-reasoning)",
            })
        elif baseline_best_non_reasoning in phantom:
            replacements.append({
                "old": baseline_best_non_reasoning,
                "new": best_mft or "[check data]",
                "context": "baseline best model not in new data",
            })

        return {
            "status": "REPLACE_MODEL" if replacements else "KEEP",
            "replacements": replacements,
            "key_facts": {
                "best_mft_model": best_mft,
                "top_is_reasoning": False,
                "top5": [(e.get("model"), e.get("value")) for e in ranking[:5]],
            },
            "phantom_models": self._phantom({baseline_best_non_reasoning}, new_set),
        }

    # ------------------------------------------------------------------
    # Reasoning F2: Reasoning models show stronger value expression
    # ------------------------------------------------------------------
    def _verify_reasoning_f2(self, a, new_set, phantom):
        cs = a.get("cross_section", {})
        r_vs_n = cs.get("schwartz_reasoning_vs_normal", {})

        reasoning_stronger = r_vs_n.get("reasoning_stronger", False)
        baseline_pairs = BASELINE_REFS["reasoning_f2_pairs"]

        phantom_in_pairs = []
        for r_m, n_m in baseline_pairs:
            if r_m in phantom:
                phantom_in_pairs.append(r_m)
            if n_m in phantom:
                phantom_in_pairs.append(n_m)

        replacements = []
        # If any pair members are phantom, all pair examples need updating
        if phantom_in_pairs:
            replacements.append({
                "old": ", ".join(phantom_in_pairs),
                "new": "[use actual reasoning/normal model pairs from new data]",
                "context": "reasoning vs. normal comparison pair examples",
            })

        if r_vs_n:
            r_mean = r_vs_n.get("reasoning_mean_total")
            n_mean = r_vs_n.get("normal_mean_total")
            gap = (r_mean - n_mean) if (r_mean and n_mean) else 0

        status = "KEEP" if (reasoning_stronger and not replacements) else (
            "MODIFY" if not reasoning_stronger else "REPLACE_MODEL"
        )

        return {
            "status": status,
            "replacements": replacements,
            "key_facts": {
                "reasoning_stronger": reasoning_stronger,
                "reasoning_vs_normal": r_vs_n,
            },
            "phantom_models": phantom_in_pairs,
        }
