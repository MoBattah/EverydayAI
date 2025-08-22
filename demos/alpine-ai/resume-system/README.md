# Multi-Variant Resume System Demo

**AI-Powered Professional Document Generation**  
*Demonstration project for Mo Battah's AI presentation*

## 🎯 Demo Overview

This project showcases a sophisticated resume generation system that creates multiple professional variants from shared content modules. Built to demonstrate AI-assisted workflow automation and professional document generation.

## 🚀 Quick Demo

```bash
# Build single variant
./build-variant.sh tech-leadership

# Build all variants  
./build-all.sh

# View available options
./build-variant.sh --list
```

## 📁 Project Structure

```
resume-system/
├── content/                    # 📝 Modular content system
│   ├── template-header.tex     # Shared LaTeX styling
│   ├── contact.tex            # Contact information
│   ├── education.tex          # Education & certifications
│   ├── experience/            # Individual job experiences
│   │   ├── techcorp.tex      # VP Engineering role
│   │   ├── consulting.tex     # AI Consulting experience
│   │   └── startup.tex       # CTO/Founder experience
│   ├── skills/               # Skill categories
│   │   ├── leadership.tex    # Leadership competencies
│   │   └── technical.tex     # Technical expertise
│   └── summaries/            # Role-specific summaries
│       ├── tech-leadership.tex
│       └── ai-consultant.tex
├── templates/                  # 🎯 Variant templates
│   ├── tech-leadership.tex    # Technology leadership variant
│   └── ai-consultant.tex      # AI consulting variant
├── outputs/                   # 📦 Generated files
│   ├── tech-leadership/       # All formats for tech leadership
│   └── ai-consultant/         # All formats for AI consulting
└── build-variant.sh          # 🔧 Build automation
```

## 🎬 Live Demo Features

### **Modular Content Architecture**
- **Shared Components**: Contact, education, core experience
- **Variant-Specific**: Professional summaries, skills emphasis
- **Smart Templating**: Different combinations for different targets

### **Professional Output Formats**
- **PDF**: Publication-quality typography with LaTeX
- **Text**: ATS-optimized plain text extraction
- **Multiple Variants**: Different emphasis for different roles

### **Build Automation**
- **Single Command**: Generate complete resume in seconds
- **Quality Assurance**: Consistent formatting across all outputs
- **Error Handling**: Graceful fallbacks for missing dependencies

## 🎯 Available Variants

### **Tech Leadership** (`tech-leadership`)
- **Target**: VP Engineering, CTO, Technical Director roles
- **Focus**: Team scaling, technical strategy, organizational development
- **Skills**: Leadership competencies and strategic thinking

### **AI Consultant** (`ai-consultant`)  
- **Target**: AI consulting, technical advisory, innovation roles
- **Focus**: AI expertise, consulting experience, digital transformation
- **Skills**: Technical depth with AI specialization

## 💡 Presentation Talking Points

### **The Problem This Solves**
1. **Version Drift**: Multiple resume versions get out of sync
2. **Format Inconsistency**: Different formatting across applications
3. **Time Intensive**: Manual updates for each role type
4. **ATS Compatibility**: Need multiple formats for different systems

### **The AI-Enhanced Solution**
1. **Single Source of Truth**: Update content once, generate everywhere
2. **Professional Quality**: LaTeX typography rivals commercial design
3. **Rapid Iteration**: Test different summaries and emphasis quickly
4. **Automation**: Complete build in under 10 seconds

### **Technical Advantages**
- **Version Control**: All source files tracked in Git
- **Reproducible**: Same input always produces same output  
- **Scalable**: Easy to add new variants as career evolves
- **Professional**: Demonstrates technical sophistication to employers

## 🔧 Technical Implementation

### **LaTeX Modular System**
```latex
% Example template structure
\input{../content/template-header.tex}     % Shared styling
\input{../content/contact.tex}             % Contact info
\input{../content/summaries/tech-leadership.tex}  % Variant-specific summary
\section{Professional Experience}
\cvheadingstart
  \input{../content/experience/techcorp.tex}    % Relevant experience
\cvheadingend
\input{../content/skills/leadership.tex}   % Skills for this variant
```

### **Build Process**
1. **LaTeX Compilation**: Professional typography with XeLaTeX
2. **Format Conversion**: PDF to text extraction for ATS systems
3. **Quality Assurance**: Automated cleanup and validation
4. **Output Organization**: Structured directories per variant

## 🎬 Demo Script Ready

This project is optimized for live demonstration, showcasing:

- **Professional document automation**
- **AI-assisted content management** 
- **Multi-format output generation**
- **Version-controlled source content**
- **Rapid iteration capabilities**

Perfect for demonstrating how AI + modern tooling transforms traditionally manual processes into automated, professional workflows.

## 🚀 Requirements

- **pdflatex**: LaTeX compilation (included in MacTeX or TeX Live)
- **pandoc**: For Word and HTML conversion (optional, graceful fallback)
- **pdftotext**: For text extraction (optional, graceful fallback)
- **Standard Unix tools**: bash, find, etc.

Built for presentation impact and technical demonstration! 🎯