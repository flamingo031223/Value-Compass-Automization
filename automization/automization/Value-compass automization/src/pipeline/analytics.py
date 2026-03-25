"""
Finding-specific structured analytics engine.

Reads the raw DataFrames from load_excel() and computes per-finding
statistics (rankings, group comparisons, trend indicators) that are
passed to the LLM section writers as a structured, interpretable context
instead of raw record dumps.

Column-name mapping is deliberately tolerant: each helper tries several
plausible names and falls back gracefully when a column is absent.
"""
from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

SCHWARTZ_DIMS = [
    "Universalism", "Security", "Benevolence", "Self-direction",
    "Achievement", "Tradition", "Conformity", "Stimulation", "Power", "Hedonism",
]

MFT_DIMS = ["Care", "Fairness", "Sanctity", "Authority", "Loyalty"]
MFT_EVR_SUFFIXES = ["_EVR", "_evr", ""]        # try with and without suffix
MFT_AVG_CANDIDATES = [
    "EVR_Avg", "evr_avg", "Avg_EVR", "Average_EVR", "EVR_avg",
    "Avg.", "avg.", "Avg",          # actual Excel column name
]

# Risk/Safety harm categories (substrings to search in column names)
RISK_CATEGORY_KEYWORDS = {
    "Rep_Toxicity":   ["rep_tox", "representation", "toxicity"],
    "Misinfo":        ["misinfo", "misinformation"],
    "Socioeconomic":  ["socioeconomic", "socio"],
    "Info_Safety":    ["info_safety", "information_safety", "info safety", "information &"],
    "Malicious":      ["malicious"],
    "Human_Autonomy": ["human_auto", "autonomy", "integrity", "human autonomy"],
}
RISK_AVG_CANDIDATES = [
    "Safety_Avg", "ASR_Avg", "Avg_ASR", "Average_ASR", "safety_avg", "avg_asr",
    "Average", "average",           # actual Excel column name
]

# FULVA dimension pairs used in finding_1
FULVA_PAIRS: List[Tuple[str, str]] = [
    ("User-Oriented", "Self-Competence"),
    ("Social",        "Idealistic"),
    ("Ethical",       "Professional"),
]

# Patterns used to identify reasoning-enhanced models by name
REASONING_NAME_PATTERNS = ["o1", "o3", "r1", "deepseek-r", "reasoning"]


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _find_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """Return the first column from *candidates* that exists in *df*."""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _model_col(df: pd.DataFrame) -> Optional[str]:
    return _find_col(df, ["Model", "model", "Model Name", "model_name", "Models"])


def _set_model_index(df: pd.DataFrame) -> pd.DataFrame:
    """Set the model name as the DataFrame index if possible."""
    col = _model_col(df)
    if col and col in df.columns:
        return df.set_index(col)
    return df


def _top_n_asc(series: pd.Series, n: int = 5) -> List[Dict[str, Any]]:
    """Return top-n entries sorted ascending (lower = better, e.g. EVR)."""
    s = series.dropna().sort_values(ascending=True)
    return [{"model": str(m), "value": round(float(v), 3)} for m, v in s.head(n).items()]


def _top_n_desc(series: pd.Series, n: int = 5) -> List[Dict[str, Any]]:
    """Return top-n entries sorted descending (higher = better)."""
    s = series.dropna().sort_values(ascending=False)
    return [{"model": str(m), "value": round(float(v), 3)} for m, v in s.head(n).items()]


def _is_reasoning(model_name: str) -> bool:
    name_lower = str(model_name).lower()
    return any(p in name_lower for p in REASONING_NAME_PATTERNS)


# ---------------------------------------------------------------------------
# Schwartz analytics
# ---------------------------------------------------------------------------

def compute_schwartz_analytics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analytics for Schwartz Theory findings.

    Key outputs:
      dimension_ranking         : ordered list of dims by mean score, high→low
      pan_cultural_order_holds  : bool — top-4 still {Uni, Ben, Sec, Self-dir}?
      low_priority_order_holds  : bool — bottom-3 still {Stim, Hed, Power}?
      dimension_leaders         : per-dim, which model scores highest
      model_total_ranking       : top-5 models by sum of all dims
      safety_dim_leaders        : top-3 models by avg of Universalism/Benevolence/Security
    """
    result: Dict[str, Any] = {}
    df = _set_model_index(df)

    dims = [d for d in SCHWARTZ_DIMS if d in df.columns]
    if not dims:
        return {"error": "No Schwartz dimension columns found", "dims_found": list(df.columns)}

    # --- Overall dimension ranking ---
    dim_means = df[dims].mean().sort_values(ascending=False)
    result["dimension_ranking"] = {
        "ordered": dim_means.index.tolist(),
        "values":  {k: round(float(v), 3) for k, v in dim_means.items()},
    }

    # Pan-cultural order check (top-4 and bottom-3)
    expected_top4    = {"Universalism", "Benevolence", "Security", "Self-direction"}
    expected_bottom3 = {"Stimulation", "Hedonism", "Power"}
    actual_top4    = set(dim_means.index[:4].tolist())
    actual_bottom3 = set(dim_means.index[-3:].tolist())

    result["pan_cultural_order_holds"] = (expected_top4 == actual_top4)
    result["low_priority_order_holds"] = (expected_bottom3 == actual_bottom3)
    # More nuanced: how many expected dims are in actual top-4?
    result["pan_cultural_overlap"] = len(expected_top4 & actual_top4)

    # --- Per-dimension leaders (with margin vs runner-up) ---
    dim_leaders: Dict[str, Any] = {}
    for d in dims:
        top2 = df[d].dropna().nlargest(2)
        if len(top2) >= 2:
            margin = float(top2.iloc[0] - top2.iloc[1])
            dim_leaders[d] = {
                "model":         str(top2.index[0]),
                "value":         round(float(top2.iloc[0]), 3),
                "margin":        round(margin, 3),
                "runner_up":     str(top2.index[1]),
                "runner_up_value": round(float(top2.iloc[1]), 3),
            }
        elif len(top2) == 1:
            dim_leaders[d] = {
                "model": str(top2.index[0]),
                "value": round(float(top2.iloc[0]), 3),
                "margin": None,
                "runner_up": None,
                "runner_up_value": None,
            }
    result["dimension_leaders"] = dim_leaders

    # --- Model total score ranking ---
    df["_total"] = df[dims].sum(axis=1)
    result["model_total_ranking"] = _top_n_desc(df["_total"], n=5)

    # --- Safety-related dims: Universalism / Benevolence / Security ---
    safety_dims = [d for d in ["Universalism", "Benevolence", "Security"] if d in df.columns]
    if safety_dims:
        result["safety_dim_leaders"] = _top_n_desc(df[safety_dims].mean(axis=1), n=3)

    # --- Reasoning vs. non-reasoning breakdown ---
    r_mask  = df.index.map(_is_reasoning).astype(bool)
    nr_mask = ~r_mask
    if r_mask.any() and nr_mask.any():
        result["reasoning_vs_normal_total"] = {
            "reasoning_mean":  round(float(df.loc[r_mask,  "_total"].mean()), 3),
            "normal_mean":     round(float(df.loc[nr_mask, "_total"].mean()), 3),
            "reasoning_stronger": float(df.loc[r_mask, "_total"].mean()) >
                                  float(df.loc[nr_mask, "_total"].mean()),
        }

    return result


# ---------------------------------------------------------------------------
# MFT analytics
# ---------------------------------------------------------------------------

def compute_mft_analytics(
    df: pd.DataFrame,
    model_info: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Analytics for MFT findings.  EVR is "Empirical Violation Ratio":
    lower EVR = better moral alignment.

    Key outputs:
      model_ranking_by_evr_avg  : top-5 models (ascending EVR — lower is better)
      best_model / best_evr_avg : #1 model and its EVR
      top_runner_up_gap         : gap (pp) between #1 and #2
      large_gap                 : bool — gap > 10 pp
      hardest_dimensions        : 2 dims with highest mean EVR
      easiest_dimensions        : 2 dims with lowest mean EVR
      model_weak_dimensions     : {model: worst_dim}
      evr_by_type               : {Open/Close: mean EVR}
      reasoning_vs_normal_evr   : {reasoning/normal mean EVR, reasoning_better bool}
    """
    result: Dict[str, Any] = {}
    df = _set_model_index(df)

    # Find EVR columns
    evr_cols: List[str] = []
    for dim in MFT_DIMS:
        for suf in MFT_EVR_SUFFIXES:
            cname = dim + suf
            if cname in df.columns:
                evr_cols.append(cname)
                break

    avg_col = _find_col(df, MFT_AVG_CANDIDATES)

    if not evr_cols and avg_col is None:
        return {"error": "No MFT EVR columns found", "cols_found": list(df.columns)}

    # --- Overall model ranking by EVR_Avg (lower = better) ---
    if avg_col:
        ranked = df[avg_col].dropna().sort_values(ascending=True)
        result["model_ranking_by_evr_avg"] = _top_n_asc(df[avg_col], n=5)

        result["best_model"]       = str(ranked.index[0])
        result["best_evr_avg"]     = round(float(ranked.iloc[0]), 2)

        if len(ranked) > 1:
            result["runner_up_model"]   = str(ranked.index[1])
            result["runner_up_evr_avg"] = round(float(ranked.iloc[1]), 2)
            gap = float(ranked.iloc[1]) - float(ranked.iloc[0])
            result["top_runner_up_gap"] = round(gap, 2)
            result["large_gap"]         = gap > 10.0   # >10 pp = dominant lead

    # --- Per-dimension stats ---
    if evr_cols:
        dim_means = df[evr_cols].mean().sort_values(ascending=False)
        result["hardest_dimensions"] = dim_means.head(2).index.tolist()  # highest EVR
        result["easiest_dimensions"] = dim_means.tail(2).index.tolist()  # lowest EVR
        result["dimension_evr_means"] = {
            c: round(float(v), 2) for c, v in dim_means.items()
        }

        # Worst dimension per model
        model_weak: Dict[str, str] = {}
        for model in df.index:
            row = df.loc[model, evr_cols]
            if row.notna().any():
                model_weak[str(model)] = str(row.idxmax())
        result["model_weak_dimensions"] = model_weak

    # --- Open vs. closed comparison ---
    if model_info is not None and avg_col:
        result.update(_type_comparison_mft(df, model_info, avg_col))

    # --- Reasoning vs. non-reasoning ---
    if avg_col:
        r_mask  = df.index.map(_is_reasoning).astype(bool)
        nr_mask = ~r_mask
        if r_mask.any() and nr_mask.any():
            r_mean  = float(df[avg_col][r_mask].mean())
            nr_mean = float(df[avg_col][nr_mask].mean())
            result["reasoning_vs_normal_evr"] = {
                "reasoning_mean_evr": round(r_mean, 2),
                "normal_mean_evr":    round(nr_mean, 2),
                # For EVR: lower = better, so reasoning_better if r_mean < nr_mean
                "reasoning_better":   r_mean < nr_mean,
            }

    return result


def _type_comparison_mft(
    df: pd.DataFrame,
    model_info: pd.DataFrame,
    avg_col: str,
) -> Dict[str, Any]:
    """Join MFT df with model info to compute EVR by type (Open/Close)."""
    mi = _set_model_index(model_info)
    type_col = _find_col(mi, ["Type", "type", "Model Type", "model_type"])
    if type_col is None:
        return {}
    df_with_type = df[[avg_col]].join(mi[[type_col]], how="left")
    if type_col not in df_with_type.columns:
        return {}
    group = df_with_type.groupby(type_col)[avg_col].mean()
    return {"evr_by_type": {str(k): round(float(v), 2) for k, v in group.items()}}


# ---------------------------------------------------------------------------
# Risk / Safety analytics
# ---------------------------------------------------------------------------

def _find_risk_col(df: pd.DataFrame, keywords: List[str]) -> Optional[str]:
    """Find a column containing any of the given keywords (case-insensitive)."""
    for col in df.columns:
        col_lower = col.lower()
        if any(kw.lower() in col_lower for kw in keywords):
            return col
    return None


def compute_risk_analytics(
    df: pd.DataFrame,
    model_info: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Analytics for Safety Taxonomy findings (ASR: lower = safer).

    Key outputs:
      pct_models_above_90_safety : % of models with safety score > 90
      ceiling_effect             : bool
      top_safety_models          : top-3 safest models
      hardest_categories         : 2 categories with highest mean ASR
      easiest_categories         : 2 categories with lowest mean ASR
      category_ranking           : {category: mean_ASR}
      safety_by_type             : {Open/Close: mean_safety_score}
    """
    result: Dict[str, Any] = {}
    df = _set_model_index(df)

    avg_col = _find_col(df, RISK_AVG_CANDIDATES)

    # Find per-category columns
    cat_cols: Dict[str, str] = {}
    for cat_key, kws in RISK_CATEGORY_KEYWORDS.items():
        col = _find_risk_col(df, kws)
        if col:
            cat_cols[cat_key] = col

    if avg_col is None and not cat_cols:
        return {"error": "No Risk/Safety columns found", "cols_found": list(df.columns)}

    # --- Determine safety score from avg_col ---
    if avg_col:
        raw = df[avg_col].dropna()
        mean_val = float(raw.mean())

        # Heuristic: if mean < 2 → fraction ASR; if < 50 → % ASR; else → direct safety score
        if mean_val < 2:
            safety_scores = (1 - raw) * 100
        elif mean_val < 50:
            safety_scores = 100 - raw
        else:
            safety_scores = raw  # already a safety score (higher = better)

        pct_above_90 = float((safety_scores > 90).mean() * 100)
        result["pct_models_above_90_safety"] = round(pct_above_90, 1)
        result["ceiling_effect"] = pct_above_90 > 70  # majority above 90

        result["top_safety_models"] = _top_n_desc(safety_scores, n=3)

        # --- Open vs. closed ---
        if model_info is not None:
            mi = _set_model_index(model_info)
            type_col = _find_col(mi, ["Type", "type", "Model Type", "model_type"])
            if type_col:
                df_with_type = safety_scores.to_frame("safety").join(mi[[type_col]], how="left")
                if type_col in df_with_type.columns:
                    group = df_with_type.groupby(type_col)["safety"].mean()
                    result["safety_by_type"] = {
                        str(k): round(float(v), 2) for k, v in group.items()
                    }

    # --- Per-category ranking (mean ASR, higher = more dangerous) ---
    if cat_cols:
        cat_means: Dict[str, float] = {}
        for cat_key, col in cat_cols.items():
            if col in df.columns:
                cat_means[cat_key] = round(float(df[col].mean()), 3)

        sorted_cats = sorted(cat_means, key=cat_means.get, reverse=True)  # type: ignore[arg-type]
        result["category_ranking"]   = {c: cat_means[c] for c in sorted_cats}
        result["hardest_categories"] = sorted_cats[:2]
        result["easiest_categories"] = sorted_cats[-2:]

    return result


# ---------------------------------------------------------------------------
# FULVA analytics
# ---------------------------------------------------------------------------

def compute_fulva_analytics(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Analytics for FULVA findings.

    Key outputs:
      pair_comparisons       : [{pair, mean_a, mean_b, gap, direction_holds, ...}]
      user_oriented_bias_holds : bool — all three pairs in correct direction
      model_ranking          : top-5 by average FULVA score
    """
    result: Dict[str, Any] = {}
    df = _set_model_index(df)

    # --- Pair comparisons ---
    pair_results = []
    for dim_a, dim_b in FULVA_PAIRS:
        if dim_a in df.columns and dim_b in df.columns:
            mean_a = float(df[dim_a].mean())
            mean_b = float(df[dim_b].mean())
            n_pos  = int((df[dim_a] > df[dim_b]).sum())
            pair_results.append({
                "pair":                   f"{dim_a} vs {dim_b}",
                "preferred_dim":          dim_a,
                "mean_preferred":         round(mean_a, 3),
                "mean_counterpart":       round(mean_b, 3),
                "gap":                    round(mean_a - mean_b, 3),
                "direction_holds":        mean_a > mean_b,
                "models_with_positive_gap": n_pos,
                "total_models":           len(df),
            })

    result["pair_comparisons"]          = pair_results
    result["user_oriented_bias_holds"]  = all(p["direction_holds"] for p in pair_results)
    result["n_pairs_direction_correct"] = sum(1 for p in pair_results if p["direction_holds"])

    # --- Overall model ranking by mean score across all FULVA dims ---
    numeric_cols = df.select_dtypes(include=[float, int]).columns.tolist()
    if numeric_cols:
        df["_avg"] = df[numeric_cols].mean(axis=1)
        result["model_ranking"] = _top_n_desc(df["_avg"], n=5)

    return result


# ---------------------------------------------------------------------------
# Cross-section analytics
# ---------------------------------------------------------------------------

def compute_cross_section_analytics(
    schwartz_df: Optional[pd.DataFrame],
    mft_df:      Optional[pd.DataFrame],
    risk_df:     Optional[pd.DataFrame],
    model_info_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """
    Cross-framework analytics: reasoning vs. normal, family groupings,
    open vs. closed on Schwartz.
    """
    result: Dict[str, Any] = {}

    # --- Reasoning vs. normal on Schwartz (used in Reasoning Finding 2) ---
    if schwartz_df is not None:
        s = _set_model_index(schwartz_df.copy())
        dims = [d for d in SCHWARTZ_DIMS if d in s.columns]
        if dims:
            s["_total"] = s[dims].sum(axis=1)
            r_mask  = s.index.map(_is_reasoning).astype(bool)
            nr_mask = ~r_mask
            if r_mask.any() and nr_mask.any():
                r_mean  = float(s.loc[r_mask,  "_total"].mean())
                nr_mean = float(s.loc[nr_mask, "_total"].mean())
                result["schwartz_reasoning_vs_normal"] = {
                    "reasoning_mean_total": round(r_mean, 3),
                    "normal_mean_total":    round(nr_mean, 3),
                    "reasoning_stronger":   r_mean > nr_mean,
                }

    # --- Open vs. closed on Schwartz (used in PropVsOpen Finding 2) ---
    if schwartz_df is not None and model_info_df is not None:
        result.update(
            _schwartz_by_type(schwartz_df.copy(), model_info_df.copy())
        )

    # --- Model family groupings (used in Families findings) ---
    if model_info_df is not None:
        mi = _set_model_index(model_info_df.copy())
        dev_col  = _find_col(mi, ["Developer", "developer", "Company", "company"])
        type_col = _find_col(mi, ["Type", "type", "Model Type"])

        if dev_col:
            result["model_families"] = mi[dev_col].to_dict()
        if type_col:
            result["model_types"] = mi[type_col].value_counts().to_dict()

    return result


def _schwartz_by_type(
    schwartz_df: pd.DataFrame,
    model_info: pd.DataFrame,
) -> Dict[str, Any]:
    s  = _set_model_index(schwartz_df)
    mi = _set_model_index(model_info)

    dims     = [d for d in SCHWARTZ_DIMS if d in s.columns]
    type_col = _find_col(mi, ["Type", "type", "Model Type", "model_type"])
    if not dims or type_col is None:
        return {}

    s["_total"] = s[dims].sum(axis=1)
    joined = s[["_total"]].join(mi[[type_col]], how="left")
    if type_col not in joined.columns:
        return {}

    group = joined.groupby(type_col)["_total"].mean()
    return {
        "schwartz_by_type": {str(k): round(float(v), 3) for k, v in group.items()}
    }


# ---------------------------------------------------------------------------
# Excel multi-row header parser
# ---------------------------------------------------------------------------

def _parse_benchmark_sheet(
    df: pd.DataFrame,
    header_row: int = 1,
    family_col: int = 0,
    model_col: int = 1,
    data_col_start: int = 2,
    data_col_end: Optional[int] = None,
    section_row: int = 0,
    target_section_keyword: Optional[str] = None,
) -> pd.DataFrame:
    """
    Parse a benchmark Excel sheet with multi-row headers.

    The Value Compass Excel format is:
      Row 0  : section label (e.g. "Empirical Violation Ratio (EVR) ↓") — optional
      Row 1  : column dimension names
      Row 2+ : data rows (some have NaN family name — forward-fill from above)

    Parameters
    ----------
    df                     : raw DataFrame from load_excel()
    header_row             : row index containing column names (default 1)
    family_col             : column index for family/group name (default 0)
    model_col              : column index for model name (default 1)
    data_col_start         : first column index for data (default 2)
    data_col_end           : last+1 column index for data (None = all remaining)
    section_row            : row index of section label (default 0, used to
                             identify the right column range for MFT)
    target_section_keyword : if given, select only the column block whose
                             section_row label contains this keyword

    Returns
    -------
    DataFrame with:
      - 'Model'  column: model name
      - 'Family' column: model family (forward-filled)
      - One column per data dimension, named from header_row
    """
    raw = df.copy().reset_index(drop=True)

    # --- Determine column range based on section keyword ---
    col_indices = list(range(data_col_start, len(raw.columns)))

    if target_section_keyword and section_row < len(raw):
        sec_labels = raw.iloc[section_row].tolist()
        # Find the block start: first col >= data_col_start whose sec label matches
        block_start = None
        for ci in col_indices:
            label = str(sec_labels[ci]) if ci < len(sec_labels) else ""
            if target_section_keyword.lower() in label.lower():
                block_start = ci
                break
        if block_start is not None:
            # Block ends where the next non-NaN section label appears
            block_end = len(raw.columns)
            for ci in range(block_start + 1, len(raw.columns)):
                label = str(sec_labels[ci]) if ci < len(sec_labels) else ""
                if label.strip() and label.lower() != "nan" and label != "NaN":
                    block_end = ci
                    break
            col_indices = list(range(block_start, block_end))

    if data_col_end is not None:
        col_indices = [c for c in col_indices if c < data_col_end]

    # --- Read column names from header_row ---
    if header_row < len(raw):
        header_vals = raw.iloc[header_row].tolist()
        col_name_map = {}
        for ci in col_indices:
            name = str(header_vals[ci]) if ci < len(header_vals) else f"col_{ci}"
            if name.strip() and name != "nan" and name != "NaN":
                col_name_map[ci] = name.strip()

    # --- Extract data rows (skip header rows) ---
    data_start_row = header_row + 1
    data_df = raw.iloc[data_start_row:].copy().reset_index(drop=True)

    # Forward-fill family names
    raw_cols = list(raw.columns)
    fam_col_name = raw_cols[family_col] if family_col < len(raw_cols) else raw_cols[0]
    mod_col_name = raw_cols[model_col] if model_col < len(raw_cols) else raw_cols[1]

    data_df[fam_col_name] = data_df[fam_col_name].ffill()

    # Build result
    result_rows = []
    for _, row in data_df.iterrows():
        model_name = str(row.iloc[model_col]).strip()
        if not model_name or model_name.lower() in ("nan", "none", ""):
            continue
        family_name = str(row.iloc[family_col]).strip() if family_col < len(row) else ""

        record: Dict[str, Any] = {"Model": model_name, "Family": family_name}
        for ci, dim_name in col_name_map.items():
            val = row.iloc[ci] if ci < len(row) else np.nan
            try:
                record[dim_name] = float(val)
            except (ValueError, TypeError):
                record[dim_name] = np.nan
        result_rows.append(record)

    result = pd.DataFrame(result_rows)
    # Drop rows where all data columns are NaN
    data_cols = [c for c in result.columns if c not in ("Model", "Family")]
    if data_cols:
        result = result.dropna(subset=data_cols, how="all")

    return result.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Model set extraction
# ---------------------------------------------------------------------------

def extract_model_set(df_dict: Dict[str, pd.DataFrame]) -> set:
    """Extract all unique model names across all sheets."""
    models: set = set()
    for sheet_name, df in df_dict.items():
        if "model info" in sheet_name.lower() or "model_info" in sheet_name.lower():
            continue
        try:
            parsed = _parse_benchmark_sheet(df)
            if "Model" in parsed.columns:
                new_names = {
                    str(m).strip()
                    for m in parsed["Model"].dropna()
                    if str(m).strip() and str(m).strip().lower() not in ("nan", "none", "")
                }
                models.update(new_names)
        except Exception:
            pass
    return models


# ---------------------------------------------------------------------------
# Intensity language mapping for group comparison
# ---------------------------------------------------------------------------

# (lo, hi, word) — delta units depend on the metric
_INTENSITY_PROP_VS_OPEN_MFT = [
    (20.0, float("inf"), "significantly"),
    (10.0, 20.0,         "moderately"),
    (0.0,  10.0,         "slightly"),
    (-float("inf"), 0.0, "comparably"),
]

_INTENSITY_REASONING_VS_NORMAL_MFT = [
    (10.0, float("inf"), "substantial improvements"),
    (3.0,  10.0,         "moderate improvements"),
    (-3.0, 3.0,          "limited improvements"),
    (-float("inf"), -3.0, "worse performance"),
]

_INTENSITY_INTRA_FAMILY_SCHWARTZ_STD = [
    (0.0,  0.10,         "highly similar"),
    (0.10, 0.20,         "moderately similar"),
    (0.20, float("inf"), "notably different"),
]


def _intensity(delta: float, thresholds: List[Tuple]) -> str:
    for lo, hi, word in thresholds:
        if lo <= delta < hi:
            return word
    return "unclear"


def compute_intensity_metrics(
    new_analytics: Dict[str, Any],
    baseline_analytics: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compute quantitative deltas between new and baseline analytics and map
    each delta to a qualitative intensity word.
    Used by group-comparison section writers to calibrate language strength.
    """
    result: Dict[str, Any] = {}

    # --- Proprietary vs. open-source MFT gap ---
    new_evr_by_type  = new_analytics.get("mft", {}).get("evr_by_type", {})
    base_evr_by_type = baseline_analytics.get("mft", {}).get("evr_by_type", {})

    def _oc_keys(d: Dict) -> Tuple[Optional[str], Optional[str]]:
        close = next((k for k in d if "close" in k.lower() or "prop" in k.lower()), None)
        open_ = next((k for k in d if "open" in k.lower()), None)
        return close, open_

    new_ck, new_ok = _oc_keys(new_evr_by_type)
    base_ck, base_ok = _oc_keys(base_evr_by_type)

    if new_ck and new_ok:
        # positive gap = open EVR higher = proprietary better
        new_gap = new_evr_by_type[new_ok] - new_evr_by_type[new_ck]
        result["prop_vs_open_mft_gap"]      = round(new_gap, 2)
        result["prop_vs_open_intensity"]    = _intensity(new_gap, _INTENSITY_PROP_VS_OPEN_MFT)
        if base_ck and base_ok:
            base_gap = base_evr_by_type[base_ok] - base_evr_by_type[base_ck]
            result["prop_vs_open_gap_change"] = round(new_gap - base_gap, 2)

    # --- Reasoning vs. normal MFT advantage ---
    new_rvn  = new_analytics.get("mft", {}).get("reasoning_vs_normal_evr", {})
    base_rvn = baseline_analytics.get("mft", {}).get("reasoning_vs_normal_evr", {})
    if new_rvn:
        # advantage = normal_evr - reasoning_evr  (positive = reasoning better)
        new_adv = new_rvn.get("normal_mean_evr", 0) - new_rvn.get("reasoning_mean_evr", 0)
        result["reasoning_mft_advantage"]  = round(new_adv, 2)
        result["reasoning_mft_intensity"]  = _intensity(new_adv, _INTENSITY_REASONING_VS_NORMAL_MFT)
        if base_rvn:
            base_adv = base_rvn.get("normal_mean_evr", 0) - base_rvn.get("reasoning_mean_evr", 0)
            result["reasoning_mft_advantage_change"] = round(new_adv - base_adv, 2)

    # --- Model spread on Schwartz (proxy for intra-family variance) ---
    total_ranking = new_analytics.get("schwartz", {}).get("model_total_ranking", [])
    if len(total_ranking) >= 2:
        vals = [e["value"] for e in total_ranking]
        std  = float(np.std(vals))
        result["schwartz_model_spread_std"] = round(std, 3)
        result["intra_family_intensity"]    = _intensity(std, _INTENSITY_INTRA_FAMILY_SCHWARTZ_STD)

    return result


# ---------------------------------------------------------------------------
# Cross-framework example validation
# ---------------------------------------------------------------------------

def validate_cross_framework_examples(
    mft_df: Optional[pd.DataFrame],
    risk_df: Optional[pd.DataFrame],
) -> Dict[str, Any]:
    """
    Validate canonical cross-framework correlation examples (used in OV-3).
    Returns {example_id: {still_valid, model, reason, ...}}.
    """
    result: Dict[str, Any] = {}

    if mft_df is None or risk_df is None:
        return result

    mft  = _set_model_index(mft_df.copy())
    risk = _set_model_index(risk_df.copy())

    # OV-3 canonical: o3-mini performs poorly on MFT Fairness AND Rep_Toxicity
    target = "o3-mini"
    fairness_col = next(
        (c for c in mft.columns if "fairness" in c.lower()), None
    )
    rep_tox_col = next(
        (c for c in risk.columns
         if "rep" in c.lower() and ("tox" in c.lower() or "representation" in c.lower())
         or "tox" in c.lower()),
        None,
    )

    if target in mft.index and target in risk.index and fairness_col and rep_tox_col:
        o3_fair = float(mft.loc[target, fairness_col])
        o3_rtox = float(risk.loc[target, rep_tox_col])
        mean_fair = float(mft[fairness_col].mean())
        mean_rtox = float(risk[rep_tox_col].mean())

        fair_worse = o3_fair > mean_fair  # higher EVR = worse
        rtox_worse = o3_rtox > mean_rtox  # higher ASR = worse
        still_valid = fair_worse and rtox_worse

        result["ov3_o3mini_example"] = {
            "model": target,
            "still_valid": still_valid,
            "o3_fairness_evr": round(o3_fair, 3),
            "mean_fairness_evr": round(mean_fair, 3),
            "o3_rep_tox_asr": round(o3_rtox, 4),
            "mean_rep_tox_asr": round(mean_rtox, 4),
            "reason": (
                "o3-mini still underperforms on both Fairness and Rep_Toxicity"
                if still_valid
                else "o3-mini example no longer valid — performance improved"
            ),
        }

    return result


# ---------------------------------------------------------------------------
# Open-source low scorer validation (Bug #1 fix)
# ---------------------------------------------------------------------------

def compute_open_source_low_scorers(
    schwartz_df: Optional[pd.DataFrame],
    model_info_df: Optional[pd.DataFrame],
    top_n: int = 3,
) -> List[Dict[str, Any]]:
    """
    Return the top_n Open-source models with the LOWEST Schwartz total score,
    identified strictly by the Type field in Model Info (not name heuristics).

    Used by PropVsOpen F2 to find verified 'open-source low scorers'.
    Only models whose Type == 'Open' (case-insensitive) can appear here.
    """
    if schwartz_df is None or model_info_df is None:
        return []

    s  = _set_model_index(schwartz_df.copy())
    mi = _set_model_index(model_info_df.copy())
    type_col = _find_col(mi, ["Type", "type", "Model Type", "model_type"])
    if type_col is None:
        return []

    dims = [d for d in SCHWARTZ_DIMS if d in s.columns]
    if not dims:
        return []

    s["_total"] = s[dims].sum(axis=1)
    joined = s[["_total"]].join(mi[[type_col]], how="left")
    open_mask = joined[type_col].astype(str).str.lower().str.strip() == "open"
    open_models = joined[open_mask].sort_values("_total", ascending=True)

    result = []
    for model, row in open_models.head(top_n).iterrows():
        result.append({
            "model": str(model),
            "schwartz_total": round(float(row["_total"]), 3),
            "type": "Open",
        })
    return result


def validate_model_types(
    model_names: List[str],
    model_info_df: Optional[pd.DataFrame],
) -> Dict[str, str]:
    """
    Return {model_name: actual_type} for a list of model names.
    Used to verify no Close-type model is cited as open-source.
    """
    if model_info_df is None:
        return {}
    mi = _set_model_index(model_info_df.copy())
    type_col = _find_col(mi, ["Type", "type", "Model Type", "model_type"])
    if type_col is None:
        return {}
    return {
        name: str(mi.loc[name, type_col]) if name in mi.index else "UNKNOWN"
        for name in model_names
    }


# ---------------------------------------------------------------------------
# Top-level entry point
# ---------------------------------------------------------------------------

def compute_all_analytics(df_dict: Dict[str, pd.DataFrame]) -> Dict[str, Any]:
    """
    Main entry point.  Accepts the raw dict from load_excel() and returns
    a nested analytics dict keyed by section name.

    Handles the Value Compass Excel format with multi-row headers.

    The result is passed to:
      - FindingChangeDetector.detect()
      - ReasoningAgent.reason_for_section()
      - BaseSectionWriter (as `analytics` instead of raw `data_summary`)
    """
    # Normalise sheet names for lookup
    sheets = {k.lower().strip(): v for k, v in df_dict.items()}

    def get_sheet(*names: str) -> Optional[pd.DataFrame]:
        for n in names:
            if n.lower() in sheets:
                return sheets[n.lower()].copy()
        return None

    raw_schwartz   = get_sheet("schwartz")
    raw_mft        = get_sheet("mft")
    raw_risk       = get_sheet("risk")
    raw_fulva      = get_sheet("fulva", "fulva")
    model_info_df  = get_sheet("model info", "model_info", "modelinfo")

    analytics: Dict[str, Any] = {}

    # --- Parse Schwartz (all data cols 2-11) ---
    schwartz_df: Optional[pd.DataFrame] = None
    if raw_schwartz is not None:
        try:
            schwartz_df = _parse_benchmark_sheet(raw_schwartz)
        except Exception as exc:
            analytics["schwartz"] = {"error": f"parse error: {exc}"}
            schwartz_df = None

    if schwartz_df is not None:
        try:
            analytics["schwartz"] = compute_schwartz_analytics(schwartz_df)
        except Exception as exc:
            analytics["schwartz"] = {"error": str(exc)}

    # --- Parse MFT — only EVR block (cols 2-7, "Empirical Violation Ratio") ---
    mft_df: Optional[pd.DataFrame] = None
    if raw_mft is not None:
        try:
            mft_df = _parse_benchmark_sheet(
                raw_mft,
                target_section_keyword="Empirical Violation Ratio",
            )
        except Exception as exc:
            analytics["mft"] = {"error": f"parse error: {exc}"}
            mft_df = None

    if mft_df is not None:
        try:
            analytics["mft"] = compute_mft_analytics(mft_df, model_info_df)
        except Exception as exc:
            analytics["mft"] = {"error": str(exc)}

    # --- Parse Risk (all data cols) ---
    risk_df: Optional[pd.DataFrame] = None
    if raw_risk is not None:
        try:
            risk_df = _parse_benchmark_sheet(raw_risk)
        except Exception as exc:
            analytics["risk"] = {"error": f"parse error: {exc}"}
            risk_df = None

    if risk_df is not None:
        try:
            analytics["risk"] = compute_risk_analytics(risk_df, model_info_df)
        except Exception as exc:
            analytics["risk"] = {"error": str(exc)}

    # --- Parse FULVA ---
    fulva_df: Optional[pd.DataFrame] = None
    if raw_fulva is not None:
        try:
            fulva_df = _parse_benchmark_sheet(raw_fulva)
        except Exception as exc:
            analytics["fulva"] = {"error": f"parse error: {exc}"}
            fulva_df = None

    if fulva_df is not None:
        try:
            analytics["fulva"] = compute_fulva_analytics(fulva_df)
        except Exception as exc:
            analytics["fulva"] = {"error": str(exc)}

    try:
        analytics["cross_section"] = compute_cross_section_analytics(
            schwartz_df, mft_df, risk_df, model_info_df
        )
    except Exception as exc:
        analytics["cross_section"] = {"error": str(exc)}

    # --- Cross-framework example validation ---
    try:
        analytics["cross_framework"] = validate_cross_framework_examples(mft_df, risk_df)
    except Exception as exc:
        analytics["cross_framework"] = {"error": str(exc)}

    # --- Open-source low scorers (Bug #1: type-validated, for PropVsOpen F2) ---
    try:
        analytics["open_low_scorers"] = compute_open_source_low_scorers(
            schwartz_df, model_info_df
        )
    except Exception:
        analytics["open_low_scorers"] = []

    return analytics
