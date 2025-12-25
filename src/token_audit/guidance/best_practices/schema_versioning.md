---
id: schema_versioning
title: Schema Versioning
severity: medium
category: operations
source: "MCP Specification"
keywords: [versioning, compatibility, migration, schema, breaking changes]
---

## Problem

MCP tool schemas evolve over time, causing compatibility issues:

- Breaking changes disrupt existing integrations
- Clients may send outdated parameter formats
- Responses may not match expected structures
- No clear upgrade path for consumers

## Solution

Implement semantic versioning for tool schemas with backward compatibility:

### 1. Version Field in Schema

```json
{
  "name": "search_files",
  "version": "2.1.0",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "options": {"type": "object"}
    }
  }
}
```

### 2. Backward-Compatible Evolution

**Adding optional fields** (minor version bump):
```json
{
  "name": "search_files",
  "version": "2.2.0",
  "inputSchema": {
    "properties": {
      "query": {"type": "string"},
      "options": {"type": "object"},
      "max_results": {"type": "integer", "default": 100}
    }
  }
}
```

**Breaking changes** (major version bump):
```json
{
  "name": "search_files_v3",
  "version": "3.0.0",
  "deprecates": "search_files",
  "inputSchema": {...}
}
```

### 3. Deprecation Strategy

```python
def search_files(query: str, **kwargs) -> dict:
    """Search files in the codebase.

    Deprecated: Use search_files_v3 for improved performance.
    This endpoint will be removed in version 4.0.
    """
    warnings.warn(
        "search_files is deprecated, use search_files_v3",
        DeprecationWarning
    )
    return search_files_v3(query, **kwargs)
```

## Implementation

### Version Compatibility Matrix

| Client Version | Server 2.x | Server 3.x |
|---------------|------------|------------|
| 2.0 | Full | Partial (via compat) |
| 2.1 | Full | Partial |
| 3.0 | N/A | Full |

### Migration Checklist

1. **Announce deprecation** in release notes
2. **Provide migration guide** with examples
3. **Maintain compatibility layer** for 2+ versions
4. **Monitor usage** of deprecated endpoints
5. **Remove after grace period** (minimum 2 major releases)

### Response Versioning

Include version in responses for debugging:

```json
{
  "result": {...},
  "meta": {
    "schema_version": "2.1.0",
    "server_version": "1.5.0"
  }
}
```

## Evidence

- MCP specification recommends semantic versioning
- Major cloud APIs (AWS, GCP) use dated versions for stability
- Breaking changes without versioning cause 3x more support issues
