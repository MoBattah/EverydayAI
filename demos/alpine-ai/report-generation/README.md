# AI + Quarto/LaTeX Demo Project

This project demonstrates professional document generation using AI assistance, Quarto, and LaTeX.

## 🚀 Quick Start

1. **Build the demo document:**
   ```bash
   ./build.sh
   ```

2. **View the result:**
   The PDF will open automatically (macOS) or check `output/AI_Technical_Analysis_Demo.pdf`

## 📁 Project Structure

```
alpine-ai/
├── _quarto.yml                          # Quarto project configuration
├── AI_Technical_Analysis_Demo.qmd       # Main demo document
├── build.sh                             # Build automation script
├── README.md                            # This file
└── output/                              # Generated PDFs
    └── AI_Technical_Analysis_Demo.pdf   # Professional output
```

## 🎯 What This Demonstrates

- **Professional Typography**: XeLaTeX with Times New Roman/Helvetica
- **Custom Branding**: Corporate color schemes and styling
- **Advanced Graphics**: TikZ diagrams generated programmatically
- **Automation**: Single-command document generation
- **AI Integration**: Content creation assistance workflow

## 💡 Key Features

### Document Generation
- Professional PDF output with publication-quality typography
- Custom title pages with branding
- Automated table of contents and cross-references
- Embedded diagrams and visualizations

### Technical Implementation
- Quarto for markdown + code integration
- XeLaTeX for advanced typography
- TikZ for programmatic graphics
- Version-controlled document source

### AI Workflow
- AI-assisted content creation
- Automated formatting consistency
- Rapid iteration and refinement
- Professional output in minutes

## 🛠️ Requirements

- **Quarto**: Document generation framework
- **XeLaTeX**: Typography engine (part of TeX Live)
- **System Fonts**: Times New Roman, Helvetica Neue
- **macOS/Linux**: Best font support

## 📋 For Presentations

See `PRESENTATION_NOTES.md` for:
- Complete presentation script
- Demo flow checklist
- Technical talking points
- Troubleshooting guide

## 🔧 Customization

### Changing Colors
Edit the LaTeX color definitions in the QMD header:
```latex
\definecolor{primaryblue}{RGB}{0, 102, 204}
\definecolor{accentgold}{RGB}{255, 193, 7}
```

### Updating Content
Modify `AI_Technical_Analysis_Demo.qmd` with your content while keeping the professional styling.

### Branding
Update the title page branding in the `\renewcommand{\maketitle}` section.

## 🎬 Live Demo Ready

This project is optimized for live demonstrations, showcasing how AI + modern tooling transforms technical document creation from a manual, time-intensive process into an automated, professional workflow.

**Built with AI assistance and optimized for presentation impact.**
