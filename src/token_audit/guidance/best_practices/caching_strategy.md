---
id: caching_strategy
title: Caching Strategy
severity: medium
category: efficiency
token_savings: "40-60%"
source: "token-audit smell detection"
related_smells: [LOW_CACHE_HIT, CACHE_MISS_STREAK, REDUNDANT_CALLS]
keywords: [cache, caching, repeated, duplicate, TTL, memoization]
---

## Problem

Repeated calls for the same data waste tokens and increase latency:

- Reading the same file multiple times in a session
- Querying unchanged database records
- Fetching static configuration repeatedly

token-audit detects this via:
- **LOW_CACHE_HIT**: Cache hit rate below 30%
- **CACHE_MISS_STREAK**: 5+ consecutive cache misses
- **REDUNDANT_CALLS**: Same tool called with identical parameters

## Solution

Implement caching at multiple levels:

### 1. MCP Server-Side Caching

```python
from functools import lru_cache
from datetime import datetime, timedelta

@lru_cache(maxsize=100)
def read_file(path: str) -> str:
    """Cache file contents for repeated reads."""
    return Path(path).read_text()

# Time-based cache for dynamic data
_cache = {}
_cache_ttl = {}

def get_with_ttl(key: str, fetcher, ttl_seconds: int = 60):
    now = datetime.now()
    if key in _cache and _cache_ttl.get(key, now) > now:
        return _cache[key]

    value = fetcher()
    _cache[key] = value
    _cache_ttl[key] = now + timedelta(seconds=ttl_seconds)
    return value
```

### 2. Client-Side Request Deduplication

Before making a tool call, check if the same call was made recently:

```python
# Track recent calls
recent_calls = {}

def should_call(tool: str, params: dict) -> bool:
    key = f"{tool}:{hash(frozenset(params.items()))}"
    if key in recent_calls:
        return False  # Skip duplicate
    recent_calls[key] = time.time()
    return True
```

### 3. Cache Headers (Future MCP Feature)

MCP 2.0 may support cache hints:

```json
{
  "result": {...},
  "cache": {
    "ttl": 300,
    "etag": "abc123"
  }
}
```

## Implementation

### TTL Recommendations by Data Type

| Data Type | TTL | Rationale |
|-----------|-----|-----------|
| File contents | 5 min | Files rarely change mid-session |
| Git status | 30 sec | May change with user edits |
| API responses | 1-5 min | Depends on API volatility |
| Static config | Session | Configuration rarely changes |

### Invalidation Triggers

- File write operations invalidate file read cache
- Git operations invalidate git status cache
- User explicitly requests fresh data

## Evidence

- token-audit data shows 40-60% token savings with proper caching
- Sessions with LOW_CACHE_HIT smell average 2.3x higher token usage
- REDUNDANT_CALLS pattern accounts for 15-20% of wasted tokens
