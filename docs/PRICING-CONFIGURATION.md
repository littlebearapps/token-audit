# Pricing Configuration Guide

**Last Updated**: 2025-12-13
**Version**: v0.7.0

This guide explains how to configure model pricing for cost calculation in MCP Audit.

---

## Overview

MCP Audit provides accurate cost estimation through a multi-tier pricing system:

**Key Features**:
- **Dynamic Pricing (v0.6.0)**: Auto-fetch current pricing for 2,000+ models via LiteLLM API
- **24-hour caching**: Minimize network requests while staying current
- **TOML fallback**: Define custom pricing or override API values
- **Offline mode**: Work without network access using cached/TOML pricing
- **Data quality tracking**: Know where your pricing came from (`pricing_source`)

---

## Pricing Sources (Lookup Order)

MCP Audit uses the following priority order for pricing:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | **LiteLLM API** | Fresh pricing from [LiteLLM's pricing database](https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json) (2,000+ models) |
| 2 | **API Cache** | Cached API data (valid for 24 hours by default) |
| 3 | **TOML config** | `./mcp-audit.toml` or `~/.mcp-audit/mcp-audit.toml` |
| 4 | **Built-in defaults** | Hardcoded pricing for common models |

### How It Works

1. **API enabled (default)**: Fetches from LiteLLM if cache expired, caches result
2. **Cache valid**: Uses cached pricing without network request
3. **API fails/disabled**: Falls back to TOML configuration
4. **No TOML**: Uses built-in defaults for common models

---

## Dynamic Pricing Configuration (v0.6.0)

Control LiteLLM API behavior in `mcp-audit.toml`:

```toml
[pricing.api]
enabled = true        # Enable/disable API fetching (default: true)
cache_ttl_hours = 24  # Cache duration in hours (default: 24)
offline_mode = false  # Never fetch, use cache/TOML only (default: false)
```

### Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `enabled` | `true` | Enable LiteLLM API pricing |
| `cache_ttl_hours` | `24` | Hours before cache expires |
| `offline_mode` | `false` | Skip all network requests |

### Example Configurations

**Default (recommended)** — Auto-fetch with 24h cache:
```toml
[pricing.api]
enabled = true
cache_ttl_hours = 24
```

**Offline mode** — Never fetch, use TOML/cache only:
```toml
[pricing.api]
enabled = true
offline_mode = true
```

**Disable API entirely** — TOML-only pricing:
```toml
[pricing.api]
enabled = false
```

**Frequent updates** — Refresh every 6 hours:
```toml
[pricing.api]
enabled = true
cache_ttl_hours = 6
```

### Cache Location

API pricing is cached at: `~/.mcp-audit/pricing-cache.json`

Check cache status with:
```bash
mcp-audit init
```

---

## Data Quality: Pricing Source

Session logs now include pricing source information in `data_quality`:

```json
{
  "data_quality": {
    "accuracy_level": "exact",
    "pricing_source": "api",
    "pricing_freshness": "fresh",
    "confidence": 0.99
  }
}
```

### Pricing Source Values

| Value | Description |
|-------|-------------|
| `api` | Fresh from LiteLLM API |
| `cache` | Valid cached API data |
| `cache-stale` | Expired cache (fallback) |
| `toml` | From TOML configuration |
| `built-in` | Hardcoded defaults |

### Pricing Freshness Values

| Value | Description |
|-------|-------------|
| `fresh` | Just fetched from API |
| `cached` | Valid cache |
| `stale` | Expired cache |
| `unknown` | No pricing data |

---

## TOML Pricing Configuration

### File Locations

| Priority | Location | Use Case |
|----------|----------|----------|
| 1 | `./mcp-audit.toml` | Project-specific override |
| 2 | `~/.mcp-audit/mcp-audit.toml` | User-level custom pricing |

### Configuration Format

```toml
[pricing.vendor]
"model-name" = { input = X.X, output = Y.Y, cache_create = Z.Z, cache_read = W.W }
```

**Fields**:
- `input`: Cost per million input tokens (USD)
- `output`: Cost per million output tokens (USD)
- `cache_create`: Cost per million cache creation tokens (USD) - *optional*
- `cache_read`: Cost per million cache read tokens (USD) - *optional*

**Vendors**: Group models by vendor namespace (e.g., `claude`, `openai`, `custom`)

### Adding Custom Models

TOML pricing overrides API pricing for the same model:

```toml
# Override API pricing for a specific model
[pricing.claude]
"claude-opus-4-5-20251101" = { input = 5.00, output = 25.00 }

# Add a model not in LiteLLM
[pricing.custom]
"my-fine-tuned-model" = { input = 2.0, output = 10.0 }

# Local model (zero cost)
[pricing.custom]
"llama-3-70b-local" = { input = 0.0, output = 0.0 }
```

### Creating a User Config

```bash
# Create config directory
mkdir -p ~/.mcp-audit

# Create minimal config (API + custom overrides)
cat > ~/.mcp-audit/mcp-audit.toml << 'EOF'
[pricing.api]
enabled = true
cache_ttl_hours = 24

[pricing.custom]
"my-custom-model" = { input = 1.0, output = 5.0 }
EOF
```

---

## Finding Model Pricing

### Automatic (Recommended)

With dynamic pricing enabled, MCP Audit automatically fetches current pricing for:
- **Anthropic**: Claude Opus, Sonnet, Haiku (all versions)
- **OpenAI**: GPT-4o, GPT-5.1, O-series models
- **Google**: Gemini Pro, Flash, and experimental models
- **2,000+ other models** from various providers

### Manual Reference

If you need to verify or override pricing:

| Provider | Pricing Page |
|----------|--------------|
| Anthropic | https://www.anthropic.com/pricing |
| OpenAI | https://openai.com/api/pricing/ |
| Google | https://ai.google.dev/gemini-api/docs/pricing |

---

## Validation

### Check Pricing Status

```bash
mcp-audit init
```

Example output:
```
MCP Audit Configuration Status
==============================
Version: 0.6.0

Pricing:
  Source: api (fresh)
  Models available: 2,347
  Cache expires in: 23h 14m

Tokenizer:
  Gemma: installed
```

### Automatic Warnings

MCP Audit warns when a model has no pricing configured:

```
WARNING: No pricing found for model: unknown-model-xyz
   Cost will be $0.00 for this session
```

---

## Advanced Configuration

### Exchange Rates

Add exchange rates for display purposes:

```toml
[metadata.exchange_rates]
USD_to_AUD = 1.54
USD_to_EUR = 0.92
USD_to_GBP = 0.79
```

**Note**: Exchange rates are for display only. All costs are calculated in USD.

### Metadata

```toml
[metadata]
currency = "USD"
pricing_unit = "per_million_tokens"
last_updated = "2025-12-12"
```

---

## Common Issues

### Issue 1: "No pricing data available"

**Cause**: API disabled and no TOML config found.

**Solution**: Either enable API or create TOML config:
```toml
[pricing.api]
enabled = true
```

### Issue 2: Network errors fetching pricing

**Cause**: Firewall or network blocking GitHub raw content.

**Solution**: Use offline mode with cached/TOML pricing:
```toml
[pricing.api]
enabled = true
offline_mode = true
```

### Issue 3: Stale pricing data

**Cause**: Cache expired and API fetch failed.

**Solution**: Check network connectivity, or manually refresh:
```bash
# Clear cache to force refresh
rm ~/.mcp-audit/pricing-cache.json
mcp-audit init
```

### Issue 4: "TOML support not available"

**Solution**: Install toml package (Python 3.8-3.10 only):

```bash
pip install toml
```

**Note**: Python 3.11+ has built-in `tomllib` (no installation needed)

---

## Best Practices

1. **Use dynamic pricing** (default) for automatic updates
2. **Override specific models** in TOML when needed
3. **Use offline mode** for air-gapped environments
4. **Check `mcp-audit init`** to verify pricing source
5. **Monitor `pricing_source`** in session logs for accuracy

---

## API Reference

### PricingConfig Class

**Methods**:
- `load()` - Load configuration from TOML file
- `get_model_pricing(model_name, vendor)` - Get pricing for a model
- `calculate_cost(...)` - Calculate cost for token usage
- `list_models(vendor)` - List all configured models
- `validate()` - Validate configuration structure

**Properties**:
- `pricing_data` - Dictionary of all pricing data
- `metadata` - Configuration metadata
- `loaded` - Boolean indicating if config loaded successfully
- `pricing_source` - Source of current pricing data

### PricingAPI Class (v0.6.0)

**Methods**:
- `get_pricing(model_name)` - Get pricing for a model from API/cache
- `refresh()` - Force refresh from API
- `list_models()` - List all models with API pricing
- `clear_cache()` - Clear the pricing cache

**Properties**:
- `source` - Current pricing source (api/cache/cache-stale/none)
- `freshness` - Cache freshness (fresh/cached/stale/unknown)
- `model_count` - Number of models available
- `expires_in` - Time until cache expires

---

## Support

**Issues**: Report configuration problems to:
- GitHub: https://github.com/littlebearapps/mcp-audit/issues
- Label: `pricing-config`

**Documentation**: See README.md for general usage
