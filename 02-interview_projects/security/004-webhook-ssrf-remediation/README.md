# Remediate webhook SSRF and implement regression verification

Sarah Chen, Platform Architect at Bellpost, has flagged an urgent security vulnerability in the outbound webhook subsystem. During recent penetration testing against our helpdesk platform, security researchers demonstrated that an attacker with tenant administrator privileges can register malicious webhook URLs to trigger Server-Side Request Forgery (SSRF). Specifically, bypass payloads utilizing decimal IP representations (such as http://2852039166), bracketed IPv6 encodings, and HTTP redirect chains successfully reached internal cloud metadata services at http://169.254.169.254/. In addition, the platform engineering team observed that delivery retry workers enter infinite loops when endpoints return persistent 5xx errors or fail DNS lookup.

## Your mission

You have 60 minutes to analyze the webhook dispatch pipeline, remediate the underlying SSRF vulnerabilities and retry defects, and build an automated regression test suite.

At minimum, your solution must achieve the following:
1. Harden URL validation in `app/webhooks/dispatch.py` so decimal IPs, hexadecimal notation, IPv6 enclosed addresses, and internal network ranges are strictly blocked.
2. Ensure webhook delivery cannot be redirected to internal services or cloud metadata endpoints.
3. Fix the retry mechanism in `app/webhooks/retry.py` so failure attempts are properly bounded by max attempt limits without infinite looping.
4. Expand `tests/test_webhooks.py` with comprehensive regression tests verifying security controls and legitimate webhook delivery.
5. Document your architectural choices and remediation tradeoffs in `CHOICES.md`.

## What you have

You are working directly in Bellpost's Python codebase (`workspace/`):
- `app/webhooks/dispatch.py`: Outbound webhook delivery logic and URL security filter `url_allowed`.
- `app/webhooks/retry.py`: Delivery scheduling, exponential backoff, and dead-letter handling.
- `app/webhooks/signing.py`: HMAC-SHA256 signature generation and verification routines.
- `app/webhooks/events.py`: Event payload generation and delivery record creation.
- `tests/test_webhooks.py`: Existing webhook test suite requiring expansion.

## Rules

- We expect you to use AI tools, search engines, and local test runners as you would in everyday engineering.
- Preserve legitimate webhook functionality: public HTTPS destinations and development mockhooks must continue to function normally.
- Do not modify database schemas or external API contracts unless strictly necessary.
- Record your decisions in `CHOICES.md` before your time is up. There is no single right answer for how you architect IP validation or socket pinning, but you must justify your technical choices clearly.

## What to send at minute 60

Ensure all your code modifications and test files are saved in `workspace/`. Your repository must contain your updated `app/webhooks/` modules, your expanded test suite in `tests/test_webhooks.py`, and your design rationale in `CHOICES.md`.

## How it is assessed

Your submission is evaluated across four core categories totaling 100%:

- **Root-Cause Security Remediation (35%)**: Elimination of SSRF bypass vectors, including decimal IP notations, alternative encodings, IPv6 loopback and mapped addresses, and redirect-based attacks.
- **Comprehensive Regression Test Suite (25%)**: Thorough automated pytest cases exercising malicious SSRF payloads, edge cases, and retry failure boundaries.
- **Legitimate Webhook Delivery Preservation (20%)**: Standard public webhooks and configured development endpoints deliver successfully with valid cryptographic signatures.
- **Design Documentation & Architecture Notes (20%)**: Clear explanation in `CHOICES.md` outlining your validation approach, defense-in-depth considerations, and operational tradeoffs.
