# Manual Tokenizer Installation

For users on corporate networks with restricted internet access.

## Download Options

1. **GitHub Releases** (recommended)
   - Visit: https://github.com/littlebearapps/token-audit/releases
   - Download: `gemma-tokenizer-v{version}.tar.gz`

2. **Direct link** (latest release)
   - https://github.com/littlebearapps/token-audit/releases/latest

## Installation Steps

1. Download the tarball to your machine
2. Extract the contents:
   ```bash
   tar -xzf gemma-tokenizer-v*.tar.gz
   ```
3. Create the cache directory:
   ```bash
   mkdir -p ~/.cache/token-audit
   ```
4. Copy the tokenizer:
   ```bash
   cp gemma-tokenizer/tokenizer.model ~/.cache/token-audit/
   ```
5. Verify installation:
   ```bash
   token-audit tokenizer status
   ```

## Verification

```bash
$ token-audit tokenizer status
Gemma Tokenizer Status
========================================
✓ Installed
  Location: ~/.cache/token-audit/tokenizer.model
  Source: Downloaded (persistent)

Gemini CLI Accuracy: 100% (exact match)
```

## Alternative: USB Transfer

For air-gapped environments:
1. Download on an internet-connected machine
2. Transfer via USB to the target machine
3. Follow steps 2-5 above

## Checksum Verification

Each release includes a `.sha256` checksum file:

```bash
# Download both files
curl -LO https://github.com/littlebearapps/token-audit/releases/download/v1.0.0/gemma-tokenizer-v1.0.0.tar.gz
curl -LO https://github.com/littlebearapps/token-audit/releases/download/v1.0.0/gemma-tokenizer-v1.0.0.tar.gz.sha256

# Verify checksum
sha256sum -c gemma-tokenizer-v1.0.0.tar.gz.sha256
```

## Without Tokenizer

If you don't install the tokenizer:
- **Claude Code**: Works perfectly (has native token counts)
- **Codex CLI**: Works perfectly (uses tiktoken)
- **Gemini CLI**: Works with ~95% accuracy (tiktoken fallback)

The fallback is still highly accurate for most use cases.
