---
id: tool_design
title: Purpose-Specific Tool Design
severity: medium
category: design
source: "MCP Best Practices"
related_smells: []
keywords: [tool design, CRUD, generic, specific, naming, boundaries]
---

## Problem

The "Generic CRUD" anti-pattern creates tools that are too broad:

```
create_resource(type, data)    # Too generic
update_resource(type, id, data) # Unclear purpose
delete_resource(type, id)       # Ambiguous scope
```

This leads to:
- Unclear tool purpose (AI may misuse)
- Larger schemas (more parameters = more tokens)
- Harder to optimize (can't cache generic operations)
- Poor discoverability

## Solution

Design purpose-specific tools with clear boundaries:

```
create_user(name, email, role)      # Clear purpose
update_user_email(user_id, email)   # Single responsibility
archive_user(user_id)               # Explicit action
```

### Design Principles

1. **Single Responsibility**: Each tool does one thing well
2. **Explicit Naming**: Tool name describes exactly what it does
3. **Minimal Parameters**: Only required inputs, no generic `options` objects
4. **Clear Return Types**: Predictable output structure

## Implementation

### Good Tool Design

```json
{
  "name": "search_codebase",
  "description": "Search for code patterns in the project",
  "inputSchema": {
    "type": "object",
    "properties": {
      "pattern": {"type": "string", "description": "Regex pattern to search"},
      "file_types": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["pattern"]
  }
}
```

### Anti-Pattern to Avoid

```json
{
  "name": "execute_operation",
  "description": "Execute various operations",
  "inputSchema": {
    "type": "object",
    "properties": {
      "operation": {"type": "string"},
      "target": {"type": "string"},
      "options": {"type": "object"}
    }
  }
}
```

### Refactoring Generic Tools

| Generic | Purpose-Specific |
|---------|------------------|
| `query(type, filter)` | `list_users()`, `search_orders(status)` |
| `modify(resource, changes)` | `update_settings(theme)`, `rename_file(path, name)` |
| `execute(command, args)` | `run_tests(path)`, `build_project()` |

## Evidence

- Purpose-specific tools have 40% smaller schemas on average
- AI accuracy improves with explicit tool boundaries
- MCP specification recommends atomic, well-defined operations

## Detection

token-audit does not yet have a dedicated smell pattern for generic tool design, but indicators to watch:

- **CHATTY smell**: May indicate overuse of generic tools requiring many calls to accomplish single tasks
- **Manual review**: Look for tools with generic prefixes (`_resource`, `_entity`, `execute_`, `do_`)
- **Session reports**: Review tool names - clusters of similar patterns (e.g., `create_X`, `update_X`, `delete_X` for multiple X) suggest CRUD anti-pattern

Future enhancement: Automated detection of generic tool patterns based on naming conventions and parameter similarity.
