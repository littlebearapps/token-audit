---
id: security
title: MCP Security Best Practices
severity: high
category: security
source: "Astrix Security Report 2025"
keywords: [credentials, secrets, tool poisoning, data exfiltration, authentication]
---

## Problem

MCP servers have broad access to system resources and can be vectors for security vulnerabilities:

1. **Credential Exposure**: 53% of MCP configurations use insecure credential handling (hardcoded secrets, plaintext storage)
2. **Tool Poisoning**: Malicious servers can inject harmful tool definitions
3. **Data Exfiltration**: Unvetted servers may transmit sensitive data
4. **Privilege Escalation**: Overly permissive tool access

## Solution

Implement defense-in-depth security measures:

### 1. Credential Management

Never hardcode credentials in MCP configurations:

```json
{
  "mcpServers": {
    "database": {
      "command": "mcp-server-db",
      "env": {
        "DB_PASSWORD": "${DB_PASSWORD}"
      }
    }
  }
}
```

Use environment variables or secure credential stores (macOS Keychain, 1Password CLI).

### 2. Server Vetting

Only use MCP servers from:
- Official sources (Anthropic, OpenAI, Google)
- Verified publishers with security audits
- Internal, audited implementations

### 3. Principle of Least Privilege

Configure minimal tool permissions:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "mcp-server-fs",
      "args": ["--read-only", "--allowed-paths", "/project"]
    }
  }
}
```

### 4. Network Isolation

Restrict MCP server network access:
- Use local-only servers when possible
- Firewall external connections
- Monitor outbound traffic

## Implementation

### Security Checklist

- [ ] No hardcoded credentials in config files
- [ ] All servers from trusted sources
- [ ] Minimal permission grants per server
- [ ] Regular audit of enabled servers
- [ ] Network monitoring enabled

### Detection

token-audit can detect some security issues:
- Servers with broad file system access
- Unusual network-enabled tools
- Credential patterns in configs (future feature)

## Evidence

- Astrix Security Report 2025: 53% of analyzed MCP setups had credential exposure
- OWASP MCP Security Guidelines recommend environment-based secrets
- CVE database shows increasing MCP-related vulnerabilities
