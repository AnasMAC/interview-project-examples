# Fictional Lantern product facts

These facts are authoritative for this exercise. Do not add capabilities, dates or commercial terms.

- **P1 Mobile:** static and dynamic analysis of customer-authorized Android (APK/AAB) and iOS (IPA) builds. iOS dynamic analysis requires a development or ad-hoc signed IPA. An App Store-encrypted IPA receives static analysis only; dynamic results show `not run`.
- **P2 Web:** authenticated dynamic testing (DAST) of customer-authorized web apps and REST APIs, with OpenAPI 3 import. Authentication uses a recorded login sequence or a static bearer token header. The scanner cannot complete MFA steps: MFA-protected logins need a test account with MFA disabled or a bearer token. No source-code SAST for web repositories.
- **P3 GraphQL:** there is no GraphQL-specific testing. A GraphQL endpoint is scanned only as generic HTTP, so query and mutation logic is not specifically exercised.
- **P4 Exports and integrations:** dashboard, JSON, CSV and SARIF 2.1.0 exports. Integrations: Jira Cloud (two-way status sync), Slack webhook, GitHub Actions, GitLab CI, Jenkins, and Azure DevOps via the CLI. There is no ServiceNow integration.
- **P5 CLI:** `lantern scan mobile --file <path> --plan <name>` and `lantern scan web --target <url> --auth <profile>`. The API key is read from the environment variable `LANTERN_API_KEY`. Exit codes: 0 = completed, no open finding at or above the `--fail-on` threshold; 1 = completed, at least one such finding; 2 = scan error or timeout; 3 = authentication or configuration error, such as a missing API key or missing file.
- **P6 Findings:** severity is critical, high, medium, low or info; status is open, confirmed, false_positive, fixed or risk_accepted. Severity is a prioritization label, not proof of exploitability. A scan does not guarantee a secure app or provide compliance certification.
- **P7 Roadmap and commitments:** Product owns the roadmap. Items marked "exploring" have no committed date. Sales engineers and account executives cannot promise features, dates, discounts or contract terms.
