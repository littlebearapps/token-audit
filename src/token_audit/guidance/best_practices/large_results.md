---
id: large_results
title: Large Result Filtering
severity: high
category: efficiency
token_savings: "90%+"
related_smells: [LARGE_PAYLOAD]
keywords: [filtering, pagination, truncation, large results, streaming]
---

## Problem

Tool calls returning large results consume excessive tokens:

- File reads returning entire large files
- Search results with thousands of matches
- API responses with verbose nested data
- Log queries returning full history

token-audit flags this via **LARGE_PAYLOAD** smell when single calls exceed 10K tokens.

## Solution

Implement result filtering and pagination at the tool level:

### 1. Selective Field Returns

```python
def list_files(directory: str, fields: list[str] = None) -> list[dict]:
    """List files with selective field projection."""
    files = Path(directory).iterdir()

    default_fields = ["name", "size", "modified"]
    requested = fields or default_fields

    return [
        {k: get_field(f, k) for k in requested}
        for f in files
    ]
```

### 2. Pagination

```python
def search_code(
    pattern: str,
    limit: int = 50,
    offset: int = 0
) -> dict:
    """Search with pagination."""
    all_matches = find_all_matches(pattern)

    return {
        "matches": all_matches[offset:offset + limit],
        "total": len(all_matches),
        "has_more": offset + limit < len(all_matches)
    }
```

### 3. Smart Truncation

```python
def read_file(
    path: str,
    max_lines: int = 500,
    start_line: int = 0
) -> dict:
    """Read file with line limits."""
    lines = Path(path).read_text().splitlines()

    return {
        "content": "\n".join(lines[start_line:start_line + max_lines]),
        "total_lines": len(lines),
        "truncated": len(lines) > max_lines
    }
```

### 4. Summary Mode

```python
def analyze_logs(
    path: str,
    mode: str = "summary"  # "summary" | "full" | "errors_only"
) -> dict:
    """Analyze logs with configurable detail level."""
    if mode == "summary":
        return {"error_count": 5, "warning_count": 23, "info_count": 1000}
    elif mode == "errors_only":
        return {"errors": [...]}  # Only error entries
    else:
        return {"entries": [...]}  # Full log
```

## Implementation

### Result Size Guidelines

| Tool Type | Max Tokens | Strategy |
|-----------|-----------|----------|
| File read | 5K | Truncation + line numbers |
| Search | 2K | Top N matches + total count |
| API query | 3K | Field projection |
| Logs | 1K | Summary mode default |

### Streaming for Large Data

For genuinely large results, use streaming:

```python
async def stream_file(path: str):
    """Stream file contents in chunks."""
    async with aiofiles.open(path) as f:
        while chunk := await f.read(4096):
            yield {"chunk": chunk, "done": False}
    yield {"chunk": "", "done": True}
```

## Evidence

- LARGE_PAYLOAD calls average 15K tokens vs 1.5K for filtered results
- 90%+ token reduction achievable with proper filtering
- Top 50 search results sufficient for 95% of use cases
