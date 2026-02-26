# vinted-cli

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

Fast CLI for searching [Vinted](https://www.vinted.se).

Primary target is vinted.se but can be configured to work with any Vinted country. Designed for agents, scripts, and quick terminal lookups. Minimal dependencies, structured output.

## Install

**uv (recommended):**

```bash
uv tool install git+https://github.com/Paatsu/vinted-cli.git
```

**Upgrade:**

```bash
uv tool upgrade vinted-cli
```

**From source:**

```bash
git clone https://github.com/Paatsu/vinted-cli.git
cd vinted-cli
pip install .
```

## Usage

### Search listings

```bash
vinted search "jeans"
vinted search "iphone 15" --price-max 5000
vinted search "nike" --condition very-good --sort price-asc
vinted search "dress M" --sort newest -n 10
vinted search "jacka" -o json | jq '.results[:3]'
vinted search --catalog-id 1231          # browse a category without a query
vinted search --price-max 100 --sort newest  # all cheap new listings
```

### Get item details

```bash
vinted item 1234567890
vinted item 1234567890 -o json
vinted item 1234567890 --country fr
```

### Browse filters

```bash
vinted countries                   # list all supported country codes
vinted conditions                  # list item condition filters
vinted catalogs                    # list the full catalog tree
vinted catalogs --parent-id 2994   # list subcatalogs of Electronics
```

## Output formats

| Flag | Format | Use case |
|------|--------|----------|
| (default) | Human-readable table | Terminal browsing |
| `-o json` | Compact JSON | Piping to `jq`, API consumption |
| `-o jsonl` | One JSON object per line | Streaming, log processing |

## Common options

All search commands support these shared options:

| Option | Description |
|--------|-------------|
| `--country` | Vinted country code (default: `se`, env: `VINTED_COUNTRY`) |
| `--price-min` | Minimum price |
| `--price-max` | Maximum price |
| `--condition` | Item condition filter |
| `--brand-id` | Numeric Vinted brand ID filter |
| `--size-id` | Numeric Vinted size ID filter |
| `--catalog-id` | Numeric Vinted catalog ID (category) filter |
| `--sort` | Sort order (`relevance`, `newest`, `oldest`, `price-asc`, `price-desc`) |
| `-n`, `--limit` | Max results to display |
| `-p`, `--page` | Page number |
| `-o`, `--output` | Output format (`table`, `json`, `jsonl`) |
| `--raw` | Full API response instead of slim fields |

## Supported countries

`se`, `fr`, `de`, `uk`, `pl`, `be`, `nl`, `it`, `es`, `at`, `lu`, `pt`, `cz`, `hu`, `ro`, `sk`, `lt`, `lv`, `ee`

Use `vinted countries` to list all supported country codes.

## Default country via environment variable

```bash
export VINTED_COUNTRY=de
vinted search "jacke"   # searches vinted.de
```

## Agent integration

The JSON output is designed for LLM agents and automation:

```bash
# Slim search results for an agent
vinted search "nike air max" --sort price-asc -o json | jq '.results[:5]'

# Stream listings line by line
vinted search "vintage levi" -o jsonl

# Price analysis
vinted search "iphone 15" -o json | python3 -c "
import sys, json
data = json.load(sys.stdin)
prices = [float(r['price']) for r in data['results'] if r.get('price')]
print(f'Found {data[\"total\"]} listings')
print(f'Price range: {min(prices):.0f} - {max(prices):.0f}')
print(f'Average: {sum(prices)/len(prices):.0f}')
"

# Get full item details
vinted item 1234567890 -o json
```

## License

MIT
