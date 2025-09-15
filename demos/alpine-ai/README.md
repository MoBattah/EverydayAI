# Wardrobe Database

A structured, machine-readable inventory designed for LLM-powered outfit generation and wardrobe analysis.

## Structure

```
wardrobe-db/
├── items/
│   ├── clothing/          # Individual clothing item files
│   └── shoes/             # Individual shoe item files
├── README.md              # This file
├── clothing-index.md      # Index of all clothing items, generated from individual files
└── shoes-index.md         # Index of all shoe items, generated from individual files
```

## Schema

Each item uses YAML frontmatter with the following fields:

- **uuid**: Unique identifier (brand-sku-color abbreviation)
- **itemName**: Official product name
- **brand**: Manufacturer
- **category**: Primary classification (Sweater, Pants, Boot, etc.)
- **subCategory**: Specific type (Crewneck, Chino, Chelsea Boot, etc.)
- **dominantColor**: Main color
- **accentColors**: Secondary colors (array)
- **pattern**: Visual pattern (Solid, Herringbone, Tweed, etc.)
- **material**: Fabric/material composition
- **styleFit**: Cut and silhouette (Slim, Regular, Oversized, etc.)
- **formality**: Scale 0-5 (0=Athletic, 1=Casual, 2=Smart Casual, 3=Business Casual, 4=Business Formal, 5=Formal)
- **seasonality**: Best seasons (array)
- **weather**: Ideal conditions (array)
- **sku**: Official product code
- **size**: Labeled size
- **sizeSystem**: Sizing system (UNISEX, MEN, WOMEN, US, EU, etc.)
- **purchaseDate**: YYYY-MM-DD
- **price**: Numeric value
- **purchaseLocation**: Where bought
- **imageUrl**: Link to product image

## Usage for LLM Queries

This structure enables sophisticated prompts like:

> "Create three outfits for a business casual office day when it's cool and dry. One outfit must include the Red Wing Iron Rangers. Explain the styling rationale for each combination."
