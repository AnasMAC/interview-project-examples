# Thornscan report format 2 (`--report jsonl`)

Vendor note for Thornscan 1.4, copied from
https://docs.thornscan.example.test/reports/jsonl (2026-09). Attached to the
"Integrate Thornscan" request. The sample reports next to this file were
produced by the trial job on `checkout-api` and `route-planner`: on
2026-09-22 (Thornscan 1.4.2) and on 2026-09-29 (Thornscan 1.5.0), ruleset
`thornscan-python@2026.09`. See the comments on REQ-0061 for the 09-29 runs.

## Layout

The report is **JSON Lines**: one JSON object per line, UTF-8, `\n` line
ends. It is *not* a single JSON document. Each object has a `record` field:

| `record` | Count | Meaning |
|---|---|---|
| `header` | exactly 1, first line | run metadata |
| `issue` | 0..n | one finding |
| `metric` | 0..n | scan statistics; ignore unknown names |
| `summary` | exactly 1, last line | totals; **missing if the scan was interrupted** |

New record types may be added in minor releases; consumers must skip
records they do not know. A report without a `summary` line is incomplete and
must not be treated as a clean run.

### `header`

| Field | Type | Notes |
|---|---|---|
| `tool` | string | always `"thornscan"` |
| `version` | string | scanner version, e.g. `"1.4.2"` |
| `format` | int | report format, `2` for this document |
| `root` | string | absolute path of the scanned checkout (the CI workspace) |
| `commit` | string | commit SHA if Thornscan found a Git checkout, else absent |
| `started_at` | string | ISO-8601 UTC |
| `ruleset` | string | ruleset name and version |

### `issue`

| Field | Type | Notes |
|---|---|---|
| `id` | string | `TS-0001`, ... **numbered per report; not stable between runs** (see "Following an issue across runs") |
| `check` | string | rule id, e.g. `py.sql.fstring-query`; stable |
| `severity` | string | `blocker`, `critical`, `major`, `minor`, `info` (see below) |
| `confidence` | number | 0.0-1.0 |
| `cwe` | array of string | `["CWE-89"]`; may be **empty**; when several, the first is the primary weakness |
| `title` | string | one-line message |
| `detail` | string | optional, Markdown |
| `file` | string | path **relative to `header.root`**; absolute (under `root`) for files reached through symlinks or generated code |
| `start`, `end` | object | `{"line": 42, "col": 8}`; lines are **1-based**, columns are **0-based** |
| `trace` | array | data-flow steps `{file, line, note}`, source first; the last step is the sink and equals `file`/`start` |
| `hash` | string | stable fingerprint of the issue (check, file, normalized snippet) |
| `status` | string | absent for open issues; `"suppressed"` when silenced by `thornscan.yml` or an inline `# thorn: ignore` |
| `suppression` | object | with `status: suppressed`: `{"reason", "by"}` |

Suppressed issues are reported unless the scan runs with `--hide-suppressed`.

### Following an issue across runs

`id` only identifies a line within one report: the same issue usually gets
a different `id` in the next run, and an `id` can be reused for a different
issue. To recognise an issue across runs, use `hash`, which stays the same
as long as the check, the file and the flagged code do not change.

### Severities

From most to least severe: `blocker` > `critical` > `major` > `minor` >
`info`. Note that Thornscan's `critical` is its *second* level: `blocker` is
reserved for issues with a confirmed source-to-sink flow.

### `summary`

`{"record": "summary", "issues": <issue lines incl. suppressed>, "suppressed": <n>, "duration_ms": <n>}`.
`issues` equals the number of `issue` lines in the file.

## Other outputs

`--sarif <file>` additionally writes a SARIF 2.1.0 log (beta in 1.4; no
data-flow `trace`, suppressed issues omitted). It is not enabled on our
runners; the trial job writes JSON Lines only.

## Example

```json
{"record": "header", "tool": "thornscan", "version": "1.4.2", "format": 2, "root": "/builds/payments/checkout-api", ...}
{"record": "issue", "id": "TS-0001", "check": "py.sql.fstring-query", "severity": "blocker", "cwe": ["CWE-89"], "file": "src/payments/refunds.py", "start": {"line": 42, "col": 8}, ...}
{"record": "summary", "issues": 7, "suppressed": 1, "duration_ms": 48211}
```
