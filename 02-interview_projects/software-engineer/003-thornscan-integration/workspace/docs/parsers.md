# Parser notes

Owner: Priya Raman. Format notes per scanner, for whoever touches
`ledger/parsers/` or onboards a new tool. Contracts are in
`docs/architecture.md` §4.2; this page is about the formats themselves.

## How a file finds its parser

`registry.detect` asks every registered parser to `sniff` the first few
kilobytes, in registration order (`BUILTIN_MODULES`). The file name only
breaks a tie, by suffix. CI jobs upload `report.json` or `results.xml` as
often as anything descriptive, so never rely on the name.

Rules every parser follows:

- Keep what the tool said: native severity label, path as written, rule id
  unchanged. Normalization happens later (`ledger/normalize/`).
- `cwe` only when the report states one. No guessing from the rule name.
- One file is one tool. A file that mixes tools is a `ParseError`.
- A report with zero findings is a valid, clean run: it fixes everything of
  that tool on that branch. A truncated report must therefore fail, not
  parse as empty.
- Raise `ParseError(message, source=..., line=...)` with the line number
  when you have one; the CLI prints it and CI shows it in the job log.

## Brackish and Thistle (SARIF 2.1.0)

Both SAST tools write SARIF; the tool name comes from
`runs[].tool.driver.name`, lowercased.

| | Brackish | Thistle |
|---|---|---|
| Rule ids | `BRK-SQLI-001` | `TH-INJ-SQL` |
| URIs | repo-relative, `uriBaseId: "%SRCROOT%"` | absolute in the CI workspace (`file:///builds/<group>/<repo>/...`) or relative to `originalUriBaseIds` |
| Columns | 1-based (per spec) | 0-based before Thistle 5.0 |
| CWE | rule tag `external/cwe/cwe-89` | `properties.cwe` on the result or rule |
| Severity | `level` (often only on the rule's `defaultConfiguration`) | `level` on each result |

Severity is the result `level`, falling back to
`defaultConfiguration.level`, then to SARIF's default `warning`. SARIF has
no "critical" level, so SAST findings top out at high. Results with `kind`
`pass` or `notApplicable` are not findings, and neither are results with an
accepted in-source suppression (`# brackish: ignore`).

Brackish and Thistle often report the same problem. That is handled by the
cross-tool issue key in `ledger/dedupe/`, not by the parsers
(`docs/adr/0002-cross-tool-dedupe.md`).

## Kitewatch (DAST, JSON)

Kitewatch scans the staging deployments
(`https://<repo>.staging.fernwick.example.test`).

```json
{"kitewatch": "2.9.3", "site": "https://checkout-api.staging.fernwick.example.test",
 "alerts": [{"pluginId": "KW-SQLI-001", "alert": "SQL injection (error based)",
             "risk": 5, "confidence": 3, "cweid": "89",
             "instances": [{"uri": "...", "method": "POST", "param": "order_id", "evidence": "..."}]}]}
```

- One alert per check, **one finding per instance** (URL + parameter).
- `risk` is the severity, an integer from 1 (informational) to 5
  (critical). Kitewatch severities are always numeric 1-5.
- `cweid` is a string; `"-1"` and `"0"` mean unknown.
- `confidence` is not used.
- The location is `Location.endpoint(uri, param)`; the HTTP method is kept
  in `extra`.

## Depwarden (dependencies, XML)

```xml
<report xmlns="urn:depwarden:report:4">
  <scanner name="Depwarden" version="4.3.0"/>
  <project name="checkout-api" ecosystem="pypi" manifest="requirements.lock"/>
  <dependency name="fastjwt" version="1.8.0" direct="true">
    <path>checkout-api &gt; fastjwt 1.8.0</path>
    <vulnerability id="DWA-2025-0917" severity="CRITICAL">
      <cwe>CWE-347</cwe> <title>...</title>
      <affected>&lt;1.9.0</affected> <fixed>1.9.0</fixed>
    </vulnerability>
  </dependency>
</report>
```

- Depwarden 4 uses the default namespace `urn:depwarden:report:4`;
  Depwarden 3 used a `dw:` prefix on another namespace. Match elements by
  local name.
- One finding per vulnerability per dependency; rule id is the advisory id
  (`DWA-...`), location `Location.dependency(name, version)`.
- Severity labels are NVD-style uppercase words; GitHub-sourced advisories
  say `MODERATE`, and unscored ones `UNKNOWN`.
- Without a lock file there is no resolved version, only the requested
  range from the manifest. We keep the range as the version.
- Refuse any DOCTYPE. Depwarden never writes one.

## Pentest reports (CSV)

The external pentest vendor (Harrowgate) delivers its findings table as an
Excel export; AppSec saves it as CSV and ingests it with tool `pentest`.
The importer was written by Ines Duarte during her 2025 internship.

- Expect a UTF-8 BOM, or Windows-1252 if someone re-saved it in an old
  Excel; `;` as delimiter (German Excel) or `,`.
- Quoted cells contain newlines ("Steps to reproduce").
- Header names drift between reports: `Ref`/`ID`, `Risk`/`Severity`,
  `Affected asset`/`Asset`. The importer maps known aliases.
- Severity words: `Critical`, `High`, `Medium`, `Low`, `Informational`.
- `Affected asset` is usually a URL; some retests name a file
  (`src/payments/webhooks.py:58`), which becomes a code location.
- Rows marked closed or "Retest passed" are skipped; the next report's
  absence fixes them in Ledger.
- The `team_name` column ("Payments", "Team Routing") is kept in `extra`
  with the slug derived from it; the owning team is assigned as for every
  other tool (OWNERS, else the repository's team).

## Adding a format

1. Collect two or three real reports, including an empty one and one from
   an older scanner version, and put trimmed copies in `samples/<tool>/`.
2. Write `ledger/parsers/<format>.py` exposing `PARSER`, and add it to
   `BUILTIN_MODULES`. Make `sniff` specific: it runs on every upload.
3. Add the tool's labels to `SEVERITY_TABLE` in `ledger/normalize/severity.py`.
4. Tests in `tests/parsers/`: the samples, the empty report, a truncated
   file, and a file another parser must not claim.
5. Update this page and `samples/manifest.json`.
