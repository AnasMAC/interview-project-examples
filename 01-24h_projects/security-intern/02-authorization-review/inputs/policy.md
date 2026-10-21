# Fictional Workboard policy

P1: A recognized **active** identity is required. Unknown identities return 401; inactive identities return 403.
P2: Only editor or admin roles may update task status.
P3: Every role, including administrator, is limited to its own tenant. There is no global administrator.
P4: Status is exactly `open` or `done`; invalid status returns 400. Missing task returns 404. For combinations of denials, order of checks may vary, but access must never be granted.
P5: Every denied request leaves **all tasks** unchanged. Successful update changes only the selected task's status and returns 200. No deletion/creation/title edits.
P6: Existing active red and blue editors/admins must retain their legitimate update capability.

Actor IDs represent trusted identities already established by a fictional upstream login. Assess this function, not authentication/password design. All records are synthetic. The initial requests are smoke examples; security tests are your work.
