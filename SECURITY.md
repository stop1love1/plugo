# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x.x   | Yes       |

## Reporting a Vulnerability

If you discover a security vulnerability in Plugo, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

Instead, please send an email to the project maintainers with:

1. A description of the vulnerability
2. Steps to reproduce the issue
3. Potential impact
4. Suggested fix (if any)

We will acknowledge receipt within 48 hours and work with you to understand and resolve the issue before any public disclosure.

## Security Best Practices

When deploying Plugo, follow these security practices:

- **Never commit API keys** — Use environment variables via `.env`
- **Set a strong `SECRET_KEY`** — Replace the default value
- **Restrict `CORS_ORIGINS`** — Only allow your specific domains
- **Use HTTPS** — Enable SSL/TLS for all production endpoints
- **Use `wss://`** — Use secure WebSocket connections in production
- **Enable MongoDB auth** — Set username/password for production databases
- **Keep dependencies updated** — Regularly update Python and npm packages
