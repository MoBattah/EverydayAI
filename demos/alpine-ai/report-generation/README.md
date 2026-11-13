# Report generation: Quarto and LaTeX

Turns a technical analysis written as Markdown into a typeset PDF. The source is
`AI_Technical_Analysis_Demo.qmd`; `build.sh` renders it.

This demo is about the last mile. Analysis that stays in a chat window is hard to circulate, and a
document assembled by hand drifts from the analysis it describes. A single source file that renders
to a consistent PDF fixes both.

## Quick start

Requirements: Quarto, XeLaTeX (part of TeX Live or TinyTeX), and the fonts named in the document
header (Times New Roman and Helvetica Neue). macOS has the best font coverage.

```bash
cd demos/alpine-ai/report-generation
./build.sh
```

The PDF is written to `output/AI_Technical_Analysis_Demo.pdf` and opened automatically on macOS.
`output/` is generated and is not committed. The `.qmd` source is the artifact to read and adapt.

## What it demonstrates

- **One source, one output.** The Markdown body, the LaTeX preamble and the styling live in the
  same file, so a change to the argument and a change to the layout land in one commit.
- **Programmatic diagrams.** TikZ blocks generate the figures, so a diagram is reviewed as text
  alongside the prose it supports.
- **Reproducible typography.** Page geometry, colours and fonts are declared in the document, not
  applied by hand in a word processor.

## Structure

```text
report-generation/
├── _quarto.yml
├── AI_Technical_Analysis_Demo.qmd
├── build.sh
└── README.md
```

## Customisation

Colours are declared in the QMD header:

```latex
\definecolor{primaryblue}{RGB}{0, 102, 204}
\definecolor{accentgold}{RGB}{255, 193, 7}
```

Title-page branding lives in the `\renewcommand{\maketitle}` block. Content changes go in the body
of the `.qmd`.

## Limitations

- The document depends on system fonts. On a machine without them, XeLaTeX falls back or fails;
  install the fonts or change the font declarations.
- `build.sh` opens the PDF with `open`, which is macOS-specific. The render itself is portable.
- This is a document template. Nothing here decides what the analysis should say.
