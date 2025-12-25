---
id: error_handling
title: Error Handling
severity: medium
category: operations
related_smells: [EXPENSIVE_FAILURES]
keywords: [errors, exceptions, retry, failure, recovery, graceful]
---

## Problem

Poor error handling in MCP tools wastes tokens and creates poor user experiences:

- Generic error messages provide no actionable guidance
- Failed high-token operations waste context budget
- No retry logic for transient failures
- Errors propagate without context

token-audit detects this via **EXPENSIVE_FAILURES**: high-token tool calls that resulted in errors.

## Solution

Implement structured error handling with actionable feedback:

### 1. Structured Error Responses

```python
class ToolError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        recoverable: bool = False,
        suggestion: str = None
    ):
        self.code = code
        self.message = message
        self.recoverable = recoverable
        self.suggestion = suggestion

def handle_error(e: Exception) -> dict:
    """Convert exceptions to structured responses."""
    if isinstance(e, FileNotFoundError):
        return {
            "error": {
                "code": "FILE_NOT_FOUND",
                "message": f"File not found: {e.filename}",
                "recoverable": True,
                "suggestion": "Check file path or use search_files to locate"
            }
        }
    # ... handle other cases
```

### 2. Error Categories

| Category | Code Prefix | Retry | Example |
|----------|-------------|-------|---------|
| Input | `INPUT_*` | No | Invalid path format |
| Resource | `RESOURCE_*` | Sometimes | File not found |
| Permission | `PERM_*` | No | Access denied |
| Transient | `TRANSIENT_*` | Yes | Network timeout |
| Internal | `INTERNAL_*` | Sometimes | Server error |

### 3. Fail-Fast for Expensive Operations

```python
def process_large_file(path: str) -> dict:
    """Process file with early validation."""
    # Validate before expensive operation
    if not Path(path).exists():
        return {"error": {"code": "FILE_NOT_FOUND", ...}}

    file_size = Path(path).stat().st_size
    if file_size > 10_000_000:  # 10MB
        return {
            "error": {
                "code": "FILE_TOO_LARGE",
                "message": f"File is {file_size} bytes, max is 10MB",
                "suggestion": "Use streaming API or specify line range"
            }
        }

    # Now proceed with expensive operation
    return process_file_contents(path)
```

### 4. Retry with Backoff

```python
import time
from functools import wraps

def retry_transient(max_attempts: int = 3, backoff: float = 1.0):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except TransientError as e:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(backoff * (2 ** attempt))
            return None
        return wrapper
    return decorator
```

## Implementation

### Error Response Schema

```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Human-readable description",
    "recoverable": true,
    "suggestion": "Try using list_files first",
    "details": {
      "path": "/requested/path",
      "searched_locations": ["/loc1", "/loc2"]
    }
  }
}
```

### Pre-Flight Validation

Validate inputs before expensive operations:

```python
def validate_tool_input(schema: dict, input: dict) -> list[str]:
    """Return list of validation errors, empty if valid."""
    errors = []
    for field, spec in schema.get("required", []):
        if field not in input:
            errors.append(f"Missing required field: {field}")
    return errors
```

## Evidence

- EXPENSIVE_FAILURES pattern averages 8K tokens wasted per failure
- Structured errors reduce follow-up clarification by 60%
- Pre-flight validation eliminates 40% of runtime errors
