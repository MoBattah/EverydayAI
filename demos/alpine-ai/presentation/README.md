# Automating the Mundane: presentation

Source and rendered output for the four-stage context engineering talk.

## View the deck

- `index.pdf`: the tracked, rendered deck.
- `index.qmd`: the Quarto source.
- `_quarto.yml`: project configuration. The deck renders through Beamer and XeLaTeX.

## Render it

Requirements: Quarto and a XeLaTeX installation.

```bash
cd demos/alpine-ai/presentation
quarto render index.qmd
```

Quarto writes `index.pdf` and `index.tex`. The tracked copies are the last rendered output; a local
render overwrites them, which is expected.

## Structure

```text
presentation/
├── _quarto.yml       Beamer project configuration
├── index.qmd         Slide source
├── index.pdf         Rendered deck
├── index.tex         Generated LaTeX
├── about.qmd         About the speaker
├── custom.scss       Web styling retained from an earlier RevealJS build
├── styles.css        Web styling retained from an earlier RevealJS build
├── images/           Figures used in the slides
└── _site/            Tracked output from the earlier RevealJS build
```

The `_site/` directory and the SCSS/CSS files are leftovers from a RevealJS version of the deck.
They are kept because they are already published and linked; the current build path is Beamer. A
future cleanup can remove them in one commit once nothing links to them.

## Editing

The deck is one `##` heading per slide. Edit `index.qmd`, then re-render. For a batch of line-level
revisions, [`tools/quarto-batch-edit`](../../../tools/quarto-batch-edit/) applies a whole JSON batch
atomically and can render afterwards.
