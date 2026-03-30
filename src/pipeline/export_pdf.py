import pypandoc
import os
import re
import tempfile

# ---------------------------------------------------------------------------
# LaTeX header shared by both the main report and the annotated report.
# Loaded via --include-in-header so multiple packages can be added cleanly.
# ---------------------------------------------------------------------------
_LATEX_HEADER = r"""
\usepackage{xcolor}
\usepackage{titlesec}
\usepackage{setspace}

% ── Title (H1 / \section) ── large, bold, with a thin rule underneath
\titleformat{\section}
  {\fontsize{22}{28}\bfseries\selectfont}
  {}{0em}{}[\vspace{2pt}\hrule\vspace{6pt}]

% ── Part headings (H2 / \subsection) ── bold, clearly larger than body
\titleformat{\subsection}
  {\fontsize{16}{21}\bfseries\selectfont}
  {}{0em}{}[\vspace{2pt}]

% ── Section headings (H3 / \subsubsection) ── bold, slightly above body
\titleformat{\subsubsection}
  {\fontsize{13}{17}\bfseries\selectfont}
  {}{0em}{}

% ── Paragraph spacing ──
\setlength{\parskip}{0.5em}
\setlength{\parindent}{0em}
"""


def _write_header_file() -> str:
    """Write the shared LaTeX header to a temp file and return its path."""
    f = tempfile.NamedTemporaryFile(
        suffix='.tex', mode='w', delete=False, encoding='utf-8'
    )
    f.write(_LATEX_HEADER)
    f.close()
    return f.name


def clean_markdown(text: str) -> str:
    """
    Clean markdown text to avoid LaTeX PDF generation errors.
    - Remove all non-ASCII characters (simplest & safest)
    - Remove Unicode blocks known to break LaTeX
    """
    # Remove specific dangerous characters first
    dangerous_chars = r"[◼■◆▮▯▰▱▪▫●•★☆▶►◀◁✓✔✗✘—–·•●○●●]"
    text = re.sub(dangerous_chars, "", text)

    # Remove all non-ASCII characters
    text = text.encode("ascii", "ignore").decode()

    return text


def _colorize_new_markers(text: str) -> str:
    """Replace *NEW* tokens with a prominent bold-blue [NEW] LaTeX inline."""
    new_tag = r'`\textbf{\textcolor{blue}{[NEW]}}`{=latex}'
    return text.replace('*NEW*', new_tag)


def _run_pandoc(cleaned_md: str, output_path: str) -> None:
    """Run pandoc with the shared LaTeX header and xelatex engine."""
    header_file = _write_header_file()
    try:
        pypandoc.convert_text(
            cleaned_md,
            'pdf',
            format='md',
            outputfile=output_path,
            extra_args=[
                '--standalone',
                '--pdf-engine=xelatex',
                f'--include-in-header={header_file}',
            ],
        )
    finally:
        os.unlink(header_file)


def save_as_pdf(markdown_text: str, output_path: str) -> None:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    marked_md  = _colorize_new_markers(markdown_text)
    cleaned_md = clean_markdown(marked_md)
    _run_pandoc(cleaned_md, output_path)
