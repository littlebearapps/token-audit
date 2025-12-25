---
id: tool_count_limits
title: Tool Count Limits
severity: high
category: efficiency
token_savings: "60-80%"
related_smells: [CHATTY, HIGH_MCP_SHARE]
keywords: [tool count, schema size, context, bundling, optimization]
---

## Problem

Too many tools create several issues:

1. **Context bloat**: Each tool schema consumes tokens
2. **Decision overhead**: AI must evaluate more options
3. **Slower responses**: More schemas to parse
4. **Selection errors**: Similar tools cause confusion

token-audit detects this via:
- **CHATTY**: Single tool called 20+ times (often symptom of missing aggregation)
- **HIGH_MCP_SHARE**: MCP tools consuming >80% of session tokens

### Token Impact by Tool Count

| Tool Count | Approx Schema Tokens | % of 200K Context |
|------------|---------------------|-------------------|
| 10 | 5K | 2.5% |
| 50 | 25K | 12.5% |
| 100 | 50K | 25% |
| 200 | 100K | 50% |

## Solution

Implement tool bundling and limits:

### 1. Tool Count Targets

| Session Type | Target Tools | Max Tools |
|-------------|--------------|-----------|
| Quick task | 5-10 | 20 |
| Feature work | 10-20 | 40 |
| Complex project | 20-40 | 60 |

### 2. Bundle Related Operations

Instead of individual tools:
```
list_files
create_file
read_file
update_file
delete_file
move_file
copy_file
```

Create bundled operations:
```
filesystem(operation, path, ...)  # One tool, multiple operations
```

Or use smart grouping:
```
read_files(paths: list)      # Batch reads
write_files(files: list)     # Batch writes
filesystem_query(query)      # Combined list/search
```

### 3. Lazy Tool Registration

```python
class LazyToolRegistry:
    """Register tools on-demand based on context."""

    def __init__(self):
        self.core_tools = ["read", "write", "search"]
        self.advanced_tools = {}

    def get_tools(self, context: str) -> list:
        tools = self.core_tools.copy()

        # Add context-specific tools
        if "git" in context:
            tools.extend(["git_status", "git_commit", "git_diff"])
        if "database" in context:
            tools.extend(["db_query", "db_migrate"])

        return tools
```

### 4. Schema Optimization

Reduce schema size without reducing functionality:

```json
{
  "name": "search",
  "description": "Search codebase",
  "inputSchema": {
    "type": "object",
    "properties": {
      "q": {"type": "string"},
      "t": {"type": "string", "enum": ["code", "file", "symbol"]}
    },
    "required": ["q"]
  }
}
```

Use short property names in schemas (expanded in implementation).

## Implementation

### Tool Audit Process

1. List all registered tools
2. Check usage in last 30 days (via token-audit)
3. Identify never-used tools (candidates for removal)
4. Group similar tools for bundling
5. Apply lazy loading to infrequently-used tools

### Monitoring Queries

```bash
# Find unused tools
token-audit report --show-unused-tools

# Find high-token tools
token-audit report --sort-by-schema-size

# Find chatty patterns (may need bundling)
token-audit smells --pattern CHATTY
```

### Migration Strategy

1. **Deprecate** individual tools (keep for compatibility)
2. **Introduce** bundled alternative
3. **Monitor** usage shift
4. **Remove** deprecated tools after grace period

## Evidence

- 60-80% token savings observed when reducing from 100 to 30 tools
- Bundled operations reduce call count by 40%
- Claude performs better with <50 well-designed tools than >100 granular ones
