from typing import Dict, Any, List


class NewInsightExplorer:
    """
    Explore potential new insights not present in the human report.
    Generates data-grounded insights for new models, trend reversals,
    and emerging patterns.
    """

    def explore(self, data_summary: Dict[str, Any]) -> List[str]:
        """
        Generate candidate new insights from analytics.
        Returns list of insight strings (each starting with *NEW*).
        """
        insights: List[str] = []

        # --- New model insights ---
        new_models = data_summary.get("newly_added_models", [])
        if new_models:
            insights.append(
                f"*NEW* The dataset now includes previously unseen models: "
                f"{', '.join(new_models)}. "
                f"These models should be evaluated for their position in existing "
                f"rankings before preserving prior top-performer claims."
            )

        # --- Schwartz hierarchy reversal ---
        s = data_summary.get("schwartz", {})
        if s and not s.get("pan_cultural_order_holds", True):
            ordered = s.get("dimension_ranking", {}).get("ordered", [])
            top3 = ordered[:3] if ordered else []
            insights.append(
                f"*NEW* The pan-cultural Schwartz value hierarchy shows significant "
                f"deviation from the expected Universalism/Benevolence/Security ordering. "
                f"Current top dimensions are: {', '.join(top3)}. "
                f"This departure warrants investigation into whether training data "
                f"or alignment procedures have shifted model value priors."
            )

        # --- FULVA bias reversal ---
        f = data_summary.get("fulva", {})
        if f and not f.get("user_oriented_bias_holds", True):
            failed = [
                p["pair"]
                for p in f.get("pair_comparisons", [])
                if not p.get("direction_holds")
            ]
            if failed:
                insights.append(
                    f"*NEW* The previously observed user-oriented bias in FULVA has "
                    f"partially reversed. The following dimension pairs no longer show "
                    f"the expected direction: {', '.join(failed)}. "
                    f"This may indicate a shift in model training objectives toward "
                    f"counterpart-oriented or self-competence dimensions."
                )

        # --- Safety ceiling change ---
        r = data_summary.get("risk", {})
        if r and not r.get("ceiling_effect", True):
            pct = r.get("pct_models_above_90_safety", 0)
            insights.append(
                f"*NEW* The safety ceiling effect is diminishing: only {pct:.0f}% of "
                f"models now achieve safety scores above 90, compared to a prior majority. "
                f"This suggests that static safety benchmarks are now more discriminating "
                f"as models encounter harder adversarial prompts."
            )

        # --- Intensity language hint ---
        intensity = data_summary.get("intensity_metrics", {})
        prop_intensity = intensity.get("prop_vs_open_intensity", "")
        if prop_intensity and prop_intensity != "significantly":
            insights.append(
                f"*NEW* The performance gap between proprietary and open-source models "
                f"on MFT is now '{prop_intensity}' rather than 'significant', suggesting "
                f"that the open-source ecosystem is closing the alignment gap."
            )

        reasoning_intensity = intensity.get("reasoning_mft_intensity", "")
        if reasoning_intensity and "substantial" in reasoning_intensity:
            insights.append(
                f"*NEW* Reasoning-enhanced models now show {reasoning_intensity} on "
                f"MFT moral alignment compared to standard models, indicating that "
                f"chain-of-thought reasoning processes may contribute meaningfully to "
                f"ethical constraint adherence."
            )

        return insights
