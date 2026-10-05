# Security Policy

## Supported Versions

Wumpus Archiver is pre-1.0 and only the latest code on the `main` branch is
supported. Security fixes are applied to `main`; older commits, tags and
forks do not receive backports.

| Version               | Supported |
| --------------------- | --------- |
| Latest `main`         | Yes       |
| Anything older        | No        |

## Reporting a Vulnerability

**Please do not open a public issue, pull request or discussion for a
security problem.**

Report it privately through GitHub Security Advisories:

1. Go to the **Security** tab of this repository.
2. Click **Report a vulnerability**.
3. Fill in the form and submit it.

Only the maintainers can see the report, and we can collaborate with you on a
fix and a coordinated disclosure in the private advisory.

### What to include

The more detail you can give, the faster we can triage:

- A description of the issue and its impact (what an attacker can do).
- The affected component (for example the CLI, the FastAPI backend, the
  SvelteKit portal, or the Discord scraper) and the commit or version.
- Step-by-step instructions or a proof of concept to reproduce it.
- Any relevant configuration, logs or error output, with secrets removed.
- Your suggested fix or mitigation, if you have one.

### Handling secrets

This project works with Discord bot tokens and archives of Discord server
content (messages, attachments and user data). Never paste a bot token, `.env`
contents, database files or private archive data into a public issue, pull
request or discussion, and redact them from anything you attach to a report.
If you find that a token has been exposed, revoke or regenerate it in the
Discord Developer Portal immediately.

## What to Expect

This is a volunteer-maintained project, so the timelines below are best-effort
targets rather than guarantees:

- **Acknowledgement:** within about 7 days of your report.
- **Initial assessment:** within about 14 days, including whether we consider
  it a valid vulnerability and how severe it is.
- **Fix and disclosure:** we aim to release a fix within about 90 days,
  sooner for severe issues, and will agree a disclosure date with you. You are
  welcome to be credited in the advisory.

If a report is declined, we will explain why.

## Automated Security Checks

The repository runs dependency audits (`pip-audit`, `npm audit`) and secret
scanning (gitleaks) in CI, and Dependabot proposes updates for Python, npm and
GitHub Actions dependencies.
