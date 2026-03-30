# src/pipeline/annotated_report.py
"""
Generates an annotated change-analysis PDF alongside the main report.

For every finding whose status is ADAPT / REFRESH_EXAMPLES / SIGNIFICANTLY_CHANGED:
  - Key entities (model names, numbers, dimension names) that are NEW in the
    generated text (absent from the human GT) are highlighted in yellow.
  - A green annotation paragraph after the finding explains what changed and why.

The annotated PDF is saved separately; the original report is never touched.
"""

import os
import re
from typing import Dict, Any, List

# ---------------------------------------------------------------------------
# Section key -> ordered finding-change keys (must match data_change_detector)
# ---------------------------------------------------------------------------
SECTION_FINDING_KEYS: Dict[str, List[str]] = {
    "overall_findings": ["overall_f1", "overall_f2", "overall_f3", "overall_f4", "overall_f5"],
    "schwartz":         ["schwartz_f1", "schwartz_f2"],
    "mft":              ["mft_f1", "mft_f2"],
    "safety":           ["safety_f1", "safety_f2"],
    "fulva":            ["fulva_f1", "fulva_f2"],
    "open_closed":      ["propclosed_f1", "propclosed_f2"],
    "model_families":   ["families_f1", "families_f2"],
    "reasoning":        ["reasoning_f1", "reasoning_f2"],
}

STATUS_LABELS: Dict[str, str] = {
    "KEEP":                  "KEEP -- no change from human report",
    "ADAPT":                 "ADAPT -- wording adjusted to reflect data shift",
    "REFRESH_EXAMPLES":      "REFRESH EXAMPLES -- model/value examples updated with current data",
    "SIGNIFICANTLY_CHANGED": "SIGNIFICANTLY CHANGED -- core trend has shifted; mentor review needed",
    "FREEZE":                "FREEZE -- required data missing; previous text preserved verbatim",
}

# Statuses that require an annotation block
_CHANGED_STATUSES = {"ADAPT", "REFRESH_EXAMPLES", "SIGNIFICANTLY_CHANGED"}

# Known dimension names across all frameworks
_SCHWARTZ_DIMS = {"Universalism", "Security", "Benevolence", "Self-direction",
                  "Achievement", "Tradition", "Conformity", "Stimulation", "Power", "Hedonism"}
_MFT_DIMS      = {"Care", "Fairness", "Sanctity", "Authority", "Loyalty"}
_FULVA_DIMS    = {"User-Oriented", "Self-Competence", "Social", "Idealistic",
                  "Ethical", "Professional"}
_ALL_DIMS      = _SCHWARTZ_DIMS | _MFT_DIMS | _FULVA_DIMS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in plain annotation text."""
    for ch, rep in [
        ('\\', r'\textbackslash{}'),
        ('%',  r'\%'),
        ('_',  r'\_'),
        ('&',  r'\&'),
        ('#',  r'\#'),
        ('^',  r'\^{}'),
        ('{',  r'\{'),
        ('}',  r'\}'),
        ('~',  r'\textasciitilde{}'),
    ]:
        text = text.replace(ch, rep)
    return text


def _extract_key_entities(text: str) -> set:
    """
    Extract model names, decimal numbers (>=2 significant), and dimension names.
    These are the candidates for yellow highlighting.
    """
    entities: set = set()

    # Decimal numbers  e.g. 68.36, 0.615
    for m in re.finditer(r'\b\d+\.\d+\b', text):
        entities.add(m.group())

    # Integers with >=2 digits (skip lone 1-digit numerals)
    for m in re.finditer(r'\b\d{2,}\b', text):
        entities.add(m.group())

    # Known dimension names (case-insensitive match, record canonical form)
    for dim in _ALL_DIMS:
        if re.search(r'\b' + re.escape(dim) + r'\b', text, re.IGNORECASE):
            entities.add(dim)

    # Model-name-like tokens: starts with uppercase, contains hyphens
    # e.g. GPT-4o, Claude-3.5-Sonnet, DeepSeek-R1, LLaMA-3.1-8B-Instruct
    for m in re.finditer(r'\b[A-Z][a-zA-Z0-9]*(?:-[a-zA-Z0-9\.]+)+\b', text):
        entities.add(m.group())

    # Lowercase reasoning / small model names that don't start with uppercase
    # e.g. o1, o3, o3-mini, o1-mini, r1, deepseek-r1 (when lowercased by writer)
    for m in re.finditer(r'\b(?:o[13](?:-(?:mini|pro|preview))?|r1|deepseek-r\d+)\b',
                         text, re.IGNORECASE):
        entities.add(m.group())

    return entities


def _find_new_entities(gt_text: str, generated_text: str) -> List[str]:
    """
    Return entities present in generated_text but absent from gt_text.
    These are the replacements / new additions worth highlighting.
    Sorted longest-first so multi-token replacements take priority.
    """
    gt_ents  = _extract_key_entities(gt_text)
    gen_ents = _extract_key_entities(generated_text)
    new = gen_ents - gt_ents
    return sorted(new, key=len, reverse=True)


def _apply_yellow_highlights(text: str, entities: List[str]) -> str:
    """
    Wrap each new entity in a LaTeX yellow colorbox using pandoc raw-inline syntax.

    Uses a single combined regex pass so each character position is matched at
    most once — preventing a shorter entity from being re-matched inside an
    already-replaced LaTeX block.
    Entities are sorted longest-first so longer matches take priority.
    """
    if not entities:
        return text

    # Build one alternation pattern; longest entities first (already sorted by caller)
    combined = '|'.join(r'\b' + re.escape(e) + r'\b' for e in entities)

    def _wrap(m: re.Match) -> str:
        token = m.group()
        return f'`\\colorbox{{yellow!60}}{{\\strut {token}}}`{{=latex}}'

    return re.sub(combined, _wrap, text)


def _green_annotation(status: str, reason: str, new_entities: List[str]) -> str:
    """
    Build a LaTeX raw block that renders as a green italic annotation paragraph.
    """
    label = STATUS_LABELS.get(status, status)
    # Cap reason length and escape
    reason_safe = _escape_latex(reason[:500].strip())
    label_safe  = _escape_latex(label)

    lines = [
        f"\\textbf{{[Change Analysis]}} \\textbf{{Status:}} {label_safe}.",
        f"\\textbf{{Reason:}} {reason_safe}",
    ]
    if new_entities:
        ent_str = ', '.join(_escape_latex(e) for e in new_entities[:12])
        lines.append(f"\\textbf{{Updated entities (highlighted in yellow):}} {ent_str}")

    # Join lines with LaTeX newline within the group
    body = r'\\[2pt] '.join(lines)

    return (
        "\n\n```{=latex}\n"
        "\\vspace{6pt}\n"
        "\\noindent\\rule{\\linewidth}{0.4pt}\n"
        f"{{\\color{{green!50!black}}\\small\\textit{{{body}}}}}\n"
        "\\par\\noindent\\rule{\\linewidth}{0.4pt}\n"
        "\\vspace{4pt}\n"
        "```\n\n"
    )


# ---------------------------------------------------------------------------
# Core annotator
# ---------------------------------------------------------------------------

def _get_gt_text(gt: Dict[str, Any], finding_idx: int) -> str:
    """Concatenate all GT sentence texts for finding at finding_idx (0-based)."""
    findings = gt.get("findings", [])
    if finding_idx >= len(findings):
        return ""
    return " ".join(
        s.get("text", "").strip()
        for s in findings[finding_idx].get("sentences", [])
    )


def _split_finding_blocks(section_md: str) -> List[str]:
    """
    Split a section's markdown at 'Finding N:' boundaries.
    Returns a list where element 0 is the pre-finding header,
    elements 1+ are individual finding blocks.

    Handles all common LLM output formats:
      Finding 1: title          (plain)
      **Finding 1:** title      (bold)
      ### Finding 1: title      (heading)
      Finding 1 - title         (dash separator)
      Finding 1 — title         (em-dash)
    """
    # Match: optional markdown heading markers (#), optional bold (**),
    # then "Finding N" followed by :, —, - or whitespace+word
    pattern = re.compile(
        r'(?=(?:#{1,4}\s+|\*{1,2})?Finding\s+\d+\s*(?::|—|-|\*{0,2}\s))',
        re.IGNORECASE,
    )
    return pattern.split(section_md)


def annotate_sections(
    section_map: Dict[str, str],     # {section_key: generated_section_md}
    all_gt: Dict[str, Any],
    finding_changes: Dict[str, Any],
) -> str:
    """
    Build the full annotated report markdown string.
    Unchanged findings are reproduced verbatim.
    Changed findings get yellow entity highlights + a green annotation block.
    """
    output_parts: List[str] = [
        "# Value Compass Report — Annotated Change Analysis\n\n"
        "_Findings that differ from the human ground truth are annotated below. "
        "Yellow highlights mark new or replaced entities (model names, numbers, "
        "dimensions). Green paragraphs explain the change status and rationale._\n"
    ]

    for section_key, section_md in section_map.items():
        gt          = all_gt.get(section_key, {})
        change_keys = SECTION_FINDING_KEYS.get(section_key, [])
        blocks      = _split_finding_blocks(section_md)

        annotated: List[str] = [blocks[0]] if blocks else []

        for i, block in enumerate(blocks[1:]):   # blocks[0] is header
            finding_idx = i
            change_key  = change_keys[finding_idx] if finding_idx < len(change_keys) else None
            change      = finding_changes.get(change_key, {}) if change_key else {}
            status      = change.get("status", "KEEP")
            reason      = change.get("reason", "")

            # Always compare entities against GT — the LLM may update Tier-C
            # examples (model names, numbers) even when the high-level status
            # is KEEP.  Yellow highlights apply to every finding.
            gt_text     = _get_gt_text(gt, finding_idx)
            new_ents    = _find_new_entities(gt_text, block)
            highlighted = _apply_yellow_highlights(block, new_ents)

            # Green annotation only for structurally changed findings
            if status in _CHANGED_STATUSES:
                annotation = _green_annotation(status, reason, new_ents)
                annotated.append(highlighted + annotation)
            else:
                annotated.append(highlighted)

        output_parts.append("".join(annotated))

    return "\n\n---\n\n".join(output_parts)


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------

def save_annotated_pdf(
    section_map: Dict[str, str],
    all_gt: Dict[str, Any],
    finding_changes: Dict[str, Any],
    output_path: str,
) -> None:
    """
    Generate the annotated change-analysis PDF and save it to output_path.
    Does NOT touch the original report PDF.
    """
    from src.pipeline.export_pdf import clean_markdown, _run_pandoc

    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    annotated_md = annotate_sections(section_map, all_gt, finding_changes)
    cleaned      = clean_markdown(annotated_md)
    _run_pandoc(cleaned, output_path)
    print(f"[annotated_report] Saved -> {output_path}")
