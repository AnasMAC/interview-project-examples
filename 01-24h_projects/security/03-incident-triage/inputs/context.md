# Fictional HarborDesk context and operational rules

Maya belongs to red, Leo to blue. Known sources: Maya 198.51.100.10, Leo 198.51.100.11. Source addresses are synthetic labels, not attribution evidence. Helpdesk 203.0.113.20 can revoke a session. svc-backup has a maintenance exception for `backup/red` exports from 203.0.113.10 between 08:55 and 09:10 UTC each day; it has **no** exception for `reports/blue`. Large exports outside the exception need review, including service identities. No unrelated policy exemptions.

Implement these queue rules:
- R1: At least three authentication failures followed by a success for the same actor and source within 10 minutes (inclusive). Queue for review; credential typo remains a possible explanation. A normal-source match is still a match.
- R2: Export with result `allowed` and records >= 100, except the exact maintenance exception above. Queue as large-export review.
- R3: Any allowed action using a session after a successful revoke of that session. The revoke resource `session/S-new` identifies session S-new; session on the revoke row belongs to the helpdesk actor.

Timestamp offsets must be converted to UTC before comparison. Deduplicate only identical event rows by event_id; if conflicting rows reused an ID, retain conflict evidence rather than choose silently. There is exactly one identical duplicate in the first window, none in the second. `records` is the requested record count recorded by the authorization layer. `allowed` does **not** prove response delivery, download completion or data leaving a device. `denied` is no authorized result. Logs have no MFA, user-agent, endpoint process or network-delivery evidence; avoid invented conclusions. Correlation across sessions, request_id and identities is meaningful, but no geolocation or ownership research is needed.
