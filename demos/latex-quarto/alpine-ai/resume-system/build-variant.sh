#!/bin/bash

# Multi-Variant Resume Build System - Demo Version
# Builds specific resume variants for different target roles
# Part of Mo Battah's AI + LaTeX presentation demonstration

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Available variants
AVAILABLE_VARIANTS=(
  "tech-leadership"
  "ai-consultant"
)

# Function to show usage
show_usage() {
  echo -e "${BLUE}Multi-Variant Resume Build System${NC}"
  echo "Usage: $0 [variant]"
  echo ""
  echo "Available variants:"
  for variant in "${AVAILABLE_VARIANTS[@]}"; do
    echo "  • $variant"
  done
  echo ""
  echo "Examples:"
  echo "  $0 tech-leadership    # Build technology leadership variant"
  echo "  $0 ai-consultant      # Build AI consulting variant"
  echo "  $0 --list            # Show available variants"
}

# Function to check if variant exists
variant_exists() {
  local variant="$1"
  for available in "${AVAILABLE_VARIANTS[@]}"; do
    if [[ "$available" == "$variant" ]]; then
      return 0
    fi
  done
  return 1
}

# Handle command line arguments
if [[ $# -eq 0 ]] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
  show_usage
  exit 0
fi

if [[ "$1" == "--list" ]]; then
  echo "Available variants:"
  for variant in "${AVAILABLE_VARIANTS[@]}"; do
    echo "  $variant"
  done
  exit 0
fi

VARIANT="$1"

# Validate variant
if ! variant_exists "$VARIANT"; then
  echo -e "${RED}Error: Variant '$VARIANT' not found${NC}"
  echo "Available variants: ${AVAILABLE_VARIANTS[*]}"
  exit 1
fi

# Create output directory
OUTPUT_DIR="outputs/$VARIANT"
mkdir -p "$OUTPUT_DIR"

# File paths
TEX_FILE="templates/${VARIANT}.tex"
PDF_FILE="${OUTPUT_DIR}/${VARIANT}-resume.pdf"
DOCX_FILE="${OUTPUT_DIR}/${VARIANT}-resume.docx"
TXT_FILE="${OUTPUT_DIR}/${VARIANT}-resume.txt"
HTML_FILE="${OUTPUT_DIR}/${VARIANT}-resume.html"

echo -e "${BLUE}🚀 Building Resume Variant: ${VARIANT}${NC}"
echo -e "${BLUE}=====================================${NC}"

# Check if template exists
if [[ ! -f "$TEX_FILE" ]]; then
  echo -e "${RED}Error: Template file $TEX_FILE not found${NC}"
  exit 1
fi

# Build PDF
echo -e "\n${BLUE}📄 Building PDF...${NC}"
cd templates
if pdflatex -interaction=nonstopmode -halt-on-error "${VARIANT}.tex" >/dev/null 2>&1; then
  # Run twice for references
  pdflatex -interaction=nonstopmode -halt-on-error "${VARIANT}.tex" >/dev/null 2>&1
  mv "${VARIANT}.pdf" "../$PDF_FILE"
  echo -e "${GREEN}✅ PDF generated: $PDF_FILE${NC}"
else
  echo -e "${RED}❌ PDF build failed${NC}"
  cd ..
  exit 1
fi
cd ..

# Convert to Word
echo -e "\n${BLUE}📝 Converting to Word...${NC}"
if pandoc -f latex -t docx -o "$DOCX_FILE" "$TEX_FILE" 2>/dev/null; then
  echo -e "${GREEN}✅ Word document: $DOCX_FILE${NC}"
else
  echo -e "${YELLOW}⚠️  Word conversion failed (pandoc might not be available)${NC}"
fi

# Generate HTML
echo -e "\n${BLUE}🌐 Converting to HTML...${NC}"
if pandoc -f latex -t html -o "$HTML_FILE" "$TEX_FILE" 2>/dev/null; then
  echo -e "${GREEN}✅ HTML document: $HTML_FILE${NC}"
else
  echo -e "${YELLOW}⚠️  HTML conversion failed${NC}"
fi

# Extract plain text
echo -e "\n${BLUE}📃 Extracting plain text...${NC}"
if command -v pdftotext &> /dev/null; then
  pdftotext -layout "$PDF_FILE" "$TXT_FILE"
  echo -e "${GREEN}✅ Plain text: $TXT_FILE${NC}"
elif pandoc -f latex -t plain -o "$TXT_FILE" "$TEX_FILE" 2>/dev/null; then
  echo -e "${GREEN}✅ Plain text (via pandoc): $TXT_FILE${NC}"
else
  echo -e "${YELLOW}⚠️  Text extraction failed${NC}"
fi

# Clean up auxiliary files
echo -e "\n${BLUE}🧹 Cleaning up...${NC}"
rm -f templates/*.aux templates/*.log templates/*.out templates/*.toc templates/*.fls templates/*.fdb_latexmk templates/*.synctex.gz
echo -e "${GREEN}✅ Cleaned auxiliary files${NC}"

# Summary
echo -e "\n${GREEN}🎉 Build Complete!${NC}"
echo -e "${BLUE}Variant: ${VARIANT}${NC}"
echo -e "${BLUE}Output directory: ${OUTPUT_DIR}/${NC}"
echo ""
echo "Generated files:"
[[ -f "$PDF_FILE" ]] && echo -e "  📄 PDF:  $PDF_FILE"
[[ -f "$DOCX_FILE" ]] && echo -e "  📝 Word: $DOCX_FILE"
[[ -f "$HTML_FILE" ]] && echo -e "  🌐 HTML: $HTML_FILE"
[[ -f "$TXT_FILE" ]] && echo -e "  📃 Text: $TXT_FILE"

echo -e "\n${BLUE}Ready for your presentation demo! 🚀${NC}"