---
id: statelessness
title: Statelessness
severity: medium
category: design
source: "MCP November 2025 Specification"
keywords: [stateless, state, session, idempotent, side effects]
---

## Problem

Stateful MCP servers create several issues:

- **Unpredictable behavior**: Results depend on hidden server state
- **Scaling limitations**: Can't distribute across instances
- **Recovery challenges**: State loss on restart
- **Testing complexity**: Tests must manage server state

## Solution

Design MCP tools to be stateless where possible:

### 1. Pass State Explicitly

Instead of:
```python
# BAD: Implicit state
def set_working_directory(path: str):
    global _cwd
    _cwd = path

def list_files():
    return os.listdir(_cwd)  # Depends on hidden state
```

Do this:
```python
# GOOD: Explicit state
def list_files(directory: str):
    return os.listdir(directory)  # All inputs explicit
```

### 2. Idempotent Operations

Tools should produce the same result regardless of how many times called:

```python
# GOOD: Idempotent
def ensure_directory(path: str) -> dict:
    """Create directory if it doesn't exist."""
    Path(path).mkdir(parents=True, exist_ok=True)
    return {"path": path, "exists": True}

# BAD: Not idempotent
def increment_counter() -> dict:
    global _counter
    _counter += 1  # Different result each call
    return {"count": _counter}
```

### 3. Client-Managed State

When state is necessary, let the client manage it:

```python
def search_with_cursor(
    query: str,
    cursor: str = None,  # Client provides cursor
    limit: int = 50
) -> dict:
    """Paginated search with client-managed cursor."""
    results, next_cursor = execute_search(query, cursor, limit)

    return {
        "results": results,
        "next_cursor": next_cursor,  # Client stores for next call
        "has_more": next_cursor is not None
    }
```

### 4. Transactional Side Effects

When side effects are necessary, make them atomic:

```python
def update_config(
    path: str,
    changes: dict,
    expected_version: str = None  # Optimistic locking
) -> dict:
    """Update config file atomically."""
    config = load_config(path)

    if expected_version and config.version != expected_version:
        return {
            "error": {
                "code": "VERSION_CONFLICT",
                "current_version": config.version
            }
        }

    # Atomic write via temp file + rename
    with atomic_write(path) as f:
        new_config = {**config, **changes, "version": new_version()}
        json.dump(new_config, f)

    return {"success": True, "new_version": new_config["version"]}
```

## Implementation

### Statelessness Checklist

- [ ] No global mutable state
- [ ] All inputs passed explicitly
- [ ] Operations are idempotent
- [ ] Pagination uses client-provided cursors
- [ ] Side effects are atomic

### Acceptable Server State

Some state is acceptable when:
- **Caching**: Read-only cache for performance
- **Connection pools**: Reused connections to backends
- **Configuration**: Immutable config loaded at startup

```python
# Acceptable: Read-only cache
_file_cache: dict[str, str] = {}

def read_file_cached(path: str) -> str:
    if path not in _file_cache:
        _file_cache[path] = Path(path).read_text()
    return _file_cache[path]
```

## Evidence

- MCP November 2025 spec recommends stateless design
- Stateless servers have 99.9% uptime vs 98% for stateful
- Testing effort reduced by 50% with stateless tools
