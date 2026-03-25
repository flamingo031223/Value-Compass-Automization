import pypandoc
import os
import re
import unicodedata

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
    """Replace *NEW* tokens with a blue LaTeX inline for xelatex rendering."""
    blue_new = r'`\textcolor{blue}{\textbf{[NEW]}}`{=latex}'
    return text.replace('*NEW*', blue_new)


def save_as_pdf(markdown_text, output_path):
    # Ensure folder exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Colorize *NEW* markers before ASCII cleaning (LaTeX cmds are all ASCII)
    marked_md = _colorize_new_markers(markdown_text)

    # Clean the markdown before passing to pandoc
    cleaned_md = clean_markdown(marked_md)

    # Convert markdown → pdf (xelatex; xcolor is part of standard TeX Live)
    pypandoc.convert_text(
        cleaned_md,
        'pdf',
        format='md',
        outputfile=output_path,
        extra_args=[
            '--standalone',
            '--pdf-engine=xelatex',
            '-V', 'header-includes=\\usepackage{xcolor}',
        ]
    )


