# Security Policy

## Supported Versions

We release patches for security vulnerabilities for the following versions:

| Version | Supported          |
| ------- | ------------------ |
| 0.8.x   | :white_check_mark: |
| 0.7.x   | :white_check_mark: |
| 0.6.x   | :white_check_mark: |
| < 0.6   | :x:                |

## Reporting a Vulnerability

We take the security of MCP Audit seriously. If you believe you have found a security vulnerability, please report it to us as described below.

### Please Do Not

- **Do not** open a public GitHub issue for security vulnerabilities
- **Do not** publicly disclose the vulnerability before it has been addressed

### How to Report

**Preferred Method**: Email security reports to **security@littlebearapps.com**

Please include the following information:

1. **Description**: Clear description of the vulnerability
2. **Impact**: What could an attacker do with this vulnerability?
3. **Steps to Reproduce**: Detailed steps to reproduce the issue
4. **Affected Versions**: Which versions are affected?
5. **Proof of Concept** (optional): Code or commands demonstrating the issue
6. **Suggested Fix** (optional): If you have ideas for how to fix it

### What to Expect

- **Acknowledgment**: We will acknowledge your email within 48 hours
- **Initial Assessment**: We will provide an initial assessment within 5 business days
- **Updates**: We will keep you informed of our progress
- **Resolution**: We aim to resolve critical vulnerabilities within 30 days
- **Credit**: We will credit you in the security advisory (unless you prefer to remain anonymous)

## Security Considerations

### Data Sensitivity

MCP Audit processes session data that may contain:

- **Token usage statistics** - Generally not sensitive
- **Tool names and parameters** - May reveal implementation details
- **File paths** - May reveal directory structure
- **Project names** - May reveal internal project names

### Privacy Protection

We provide built-in privacy utilities (`privacy.py`) for:

- **Redacting secrets** (API keys, tokens, passwords)
- **Sanitizing file paths** (removing user-specific paths)
- **Filtering sensitive data** before sharing session logs

**Recommendation**: Always use the privacy filters before sharing session data publicly.

### Secure Configuration

**Best Practices**:

1. **API Keys**: Never commit API keys or tokens to git
2. **Pricing Data**: Keep `mcp-audit.toml` out of public repos if pricing is proprietary
3. **Session Logs**: Review session logs before sharing (may contain sensitive context)
4. **File Permissions**: Ensure log files are only readable by your user

### Known Security Considerations

1. **Debug Logs**: May contain full conversation history including prompts and responses
2. **Event Streams**: `events.jsonl` files contain complete session data
3. **MCP Tool Names**: Tool names may reveal MCP server capabilities

## Security Features

### Implemented

- ✅ **Privacy filters** for redacting sensitive data
- ✅ **Schema versioning** for safe data format evolution
- ✅ **Input validation** on all user-supplied data
- ✅ **Type checking** with mypy strict mode
- ✅ **Static analysis** (via GitHub CodeQL)
- ✅ **Secret scanning** (via GitHub secret scanning)

### Planned

- 🔄 **Encrypted session storage** (optional)
- 🔄 **Audit logging** for file access
- 🔄 **Configurable retention policies** for sensitive data

## Vulnerability Disclosure Policy

When we receive a security vulnerability report:

1. **Validation**: We will validate the reported vulnerability
2. **Patch Development**: We will develop and test a fix
3. **Security Advisory**: We will publish a GitHub Security Advisory
4. **Version Release**: We will release a patched version
5. **Public Disclosure**: We will publicly disclose after patch is available

**Timeline**: We aim to complete this process within 30 days for critical vulnerabilities.

## Security Updates

**How to Stay Informed**:

- **GitHub Security Advisories**: Watch the repository for security advisories
- **Release Notes**: Check `CHANGELOG.md` for security-related updates
- **GitHub Releases**: Subscribe to release notifications

**Automatic Updates**:

If you have Dependabot enabled, you'll receive automated PRs for security updates.

## Security Best Practices for Users

### For Solo Developers

1. Keep session logs private (don't commit to public repos)
2. Review logs before sharing for debugging
3. Use privacy filters when sharing data
4. Keep MCP Audit updated to latest version

### For Teams

1. Establish data sharing policies
2. Use private repositories for session data
3. Configure access controls on log directories
4. Document which data is safe to share publicly

### For Open Source Projects

1. Use privacy filters before sharing session data
2. Never commit actual session logs to public repos
3. Use example/sanitized data for documentation
4. Document what data users should redact

## Threat Model

### In Scope

- Vulnerabilities in MCP Audit code
- Dependency vulnerabilities
- Security issues in data processing
- Privacy leaks in session logs
- Insecure file handling

### Out of Scope

- Vulnerabilities in MCP servers (report to respective projects)
- Issues in underlying platforms (Claude Code, Codex CLI, etc.)
- Generic security issues with Python or dependencies (report upstream)
- Social engineering attacks
- Physical access to user systems

## Contact

- **Security Issues**: security@littlebearapps.com
- **General Issues**: https://github.com/littlebearapps/mcp-audit/issues
- **General Contact**: https://littlebearapps.com

---

**Last Updated**: 2025-12-13
