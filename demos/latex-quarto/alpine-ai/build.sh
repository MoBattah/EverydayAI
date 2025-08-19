#!/bin/bash

# AI Technical Analysis Demo Build Script
# For Mo Battah's AI presentation demonstration

echo "🚀 Building AI Technical Analysis Demo..."
echo "=================================="

# Check if Quarto is installed
if ! command -v quarto &> /dev/null; then
    echo "❌ Quarto not found. Please install Quarto first."
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p output

# Build the document
echo "📄 Rendering Quarto document to PDF..."
quarto render AI_Technical_Analysis_Demo.qmd

# Check if build was successful
if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    echo "📁 Output files in: ./output/"
    
    # List output files
    echo "📋 Generated files:"
    ls -la output/
    
    # Open the PDF if on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "🔍 Opening PDF..."
        open output/AI_Technical_Analysis_Demo.pdf
    fi
else
    echo "❌ Build failed. Check the error messages above."
    exit 1
fi

echo "=================================="
echo "🎯 Demo ready for presentation!"