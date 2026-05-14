# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.0.x   | ✅ Active |
| 1.x     | ❌ EOL    |

## Reporting a Vulnerability

**Do not open a public issue.** Email the maintainer directly.

We take security seriously. Hermes Workspace includes built-in security tooling:

- **hermes-scan** — A-F security analyzer for all skills
- **hermes-audit** — execution receipt with token estimation
- **GateMem compatibility** — memory governance benchmarking

## Security Features

### Skill Scanning (hermes-scan)
Every skill in the registry undergoes automated security analysis covering:
- Permissions declaration
- Network access scope
- Cost estimation
- File system boundaries
- Audit hash verification
- Dependency safety

Skills rated E or F are blocked from the verified registry.

### Audit Trail (hermes-audit)
All skill executions generate a signed receipt containing:
- Token consumption estimate
- Tool calls made
- Timing and completion status
- Cryptographic signature

### Memory Governance (GateMem)
Shared memory supports:
- Namespace isolation (shared/personal/board/audit)
- Audit hashing on all entries
- GateMem-compatible governance export

## Responsible Disclosure

1. Email with details of the vulnerability
2. Allow up to 72 hours for acknowledgment
3. We will coordinate disclosure timeline with you
4. Credit will be given in release notes (unless you prefer anonymity)
