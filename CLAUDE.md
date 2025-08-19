# Claude Code Context: AI Presentation Project

## Project Overview
This is a Quarto-based presentation system for Mo Battah's AI presentation titled "The Asymmetric Bet: Over-Indexing on AI for Engineering and Enterprise" for Alpine Investors & Portfolio Companies.

## Repository Structure
- **Main Project**: `/Users/mo/dev/prompts/demos/latex-quarto/alpine-ai/`
- **Presentation**: `presentation/` - RevealJS-based slides
- **Report Generation**: `report-generation/` - PDF document generation demo
- **Resume System**: `resume-system/` - Modular LaTeX resume builder

## Presentation Setup Analysis

### Current Configuration (`_quarto.yml`)
- **Type**: Website with RevealJS format
- **Theme**: Default + custom.scss
- **Features**: ToC enabled, custom CSS styling
- **Status**: ✅ Successfully builds

### Issues Identified

#### 1. **Git Merge Conflict Artifacts** (CRITICAL)
- File: `index.qmd` lines 15-17
- Contains `=======` merge conflict markers
- Causes content duplication in sections

#### 2. **Content Structure Issues**
- Duplicate sections (e.g., "My Essential AI Tools" appears twice)
- Mixed organization between outline and actual content
- Navigation structure could be improved

#### 3. **Configuration Improvements Needed**
- Missing presentation metadata (author, date)
- RevealJS-specific features not fully utilized
- No slide numbering or progress indicators

### Recommendations for Best Practices

#### 1. **Clean Up Merge Conflicts**
- Remove `=======` artifacts
- Consolidate duplicate content
- Ensure consistent formatting

#### 2. **Enhance RevealJS Configuration**
```yaml
format:
  revealjs:
    theme: [default, custom.scss]
    css: styles.css
    toc: true
    slide-number: true
    show-slide-number: all
    hash-type: number
    transition: slide
    background-transition: fade
```

#### 3. **Improve Metadata**
```yaml
---
title: "The Asymmetric Bet: Over-Indexing on AI for Engineering and Enterprise"
subtitle: "Alpine Investors & Portfolio Companies"
author: "Mo Battah"
date: "2025-08-20"
format: revealjs
---
```

#### 4. **Content Organization**
- Use clear slide breaks (`---`)
- Implement hierarchical structure
- Separate speaker notes from slide content

## Technical Environment
- **Quarto**: v1.7.31 ✅
- **LaTeX**: TinyTeX 2025 ✅
- **Pandoc**: v3.6.3 ✅
- **Build Status**: Successfully renders to HTML

## Related Demos
- **Report Generation**: Professional PDF output using XeLaTeX
- **Resume System**: Modular LaTeX system with build scripts
- **Prompt Library**: OSINT and linguistics prompts

## Next Steps Priority
1. Fix merge conflict artifacts
2. Restructure content for clear slide flow
3. Enhance RevealJS configuration
4. Add proper metadata
5. Test presentation flow and timing