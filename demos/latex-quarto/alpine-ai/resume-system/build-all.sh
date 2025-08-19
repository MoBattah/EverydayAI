#!/bin/bash

# Build All Resume Variants - Demo Version
# Generates all resume variants for comprehensive demonstration
# Part of Mo Battah's AI + LaTeX presentation system

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# All available variants
VARIANTS=(
  "tech-leadership"
  "ai-consultant"
)

echo -e "${BLUE}🚀 Building All Resume Variants${NC}"
echo -e "${BLUE}==============================${NC}"
echo -e "Variants to build: ${#VARIANTS[@]}"
echo ""

# Track build statistics
TOTAL_VARIANTS=${#VARIANTS[@]}
SUCCESSFUL_BUILDS=0
FAILED_BUILDS=0

# Build each variant
for variant in "${VARIANTS[@]}"; do
  echo -e "\n${BLUE}📋 Building variant: ${variant}${NC}"
  echo "----------------------------------------"
  
  if ./build-variant.sh "$variant"; then
    ((SUCCESSFUL_BUILDS++))
    echo -e "${GREEN}✅ Successfully built: ${variant}${NC}"
  else
    ((FAILED_BUILDS++))
    echo -e "${RED}❌ Failed to build: ${variant}${NC}"
  fi
done

# Final summary
echo -e "\n${BLUE}📊 Build Summary${NC}"
echo -e "${BLUE}================${NC}"
echo -e "Total variants: ${TOTAL_VARIANTS}"
echo -e "${GREEN}Successful: ${SUCCESSFUL_BUILDS}${NC}"
if [[ $FAILED_BUILDS -gt 0 ]]; then
  echo -e "${RED}Failed: ${FAILED_BUILDS}${NC}"
fi

# Count total files generated
TOTAL_FILES=$(find outputs -name "*.pdf" -o -name "*.docx" -o -name "*.html" -o -name "*.txt" | wc -l)
echo -e "\n${GREEN}🎉 Generated ${TOTAL_FILES} total files across all formats!${NC}"

# List output structure
echo -e "\n${BLUE}📁 Output Structure:${NC}"
echo "outputs/"
for variant in "${VARIANTS[@]}"; do
  if [[ -d "outputs/$variant" ]]; then
    echo "├── $variant/"
    find "outputs/$variant" -type f | head -4 | sed 's/^/│   ├── /'
  fi
done

echo -e "\n${GREEN}All variants ready for presentation! 🚀${NC}"
echo -e "${BLUE}Perfect for demonstrating AI-assisted resume automation.${NC}"