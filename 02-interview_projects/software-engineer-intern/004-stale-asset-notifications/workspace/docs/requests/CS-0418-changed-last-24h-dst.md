# CS-0418: "Changed in last 24h" shows the wrong assets (Toronto)

| | |
|---|---|
| From | Omar Haddad (customer success) |
| Date | 2026-11-02 |
| Customer | Harborview Bank (`harborview-bank`, America/Toronto) |
| Priority | Medium; their night shift uses this view for hand-over |
| Status | Needs investigation |

## Customer report

> Our night analyst opened the "Changed in last 24h" saved view at 00:10 on
> Monday 2 November. It listed `vpn.harborview-bank.example.test`, whose
> only change was at 00:40 on Sunday, more than 24 hours earlier. The
> digest our SIEM pulls from the API with the same filter
> (`changed_within=24`) had the same extra assets. On Friday evening the
> view was fine. Is the 24 hours really 24 hours?
> -- Harborview SOC

## What I know

- Toronto changed from daylight time to standard time on Sunday
  2026-11-01 at 02:00 (clocks went back to 01:00). Quillstone (London) did
  the same on 25 October; Orchid (Auckland) moved forward on 27 September.
  Nobody else has reported anything, but nobody else uses the view at night.
- The SOC's times are Toronto local times. The asset's history in the
  dashboard shows the change at 04:40 UTC on 1 November.
- The dashboard link and the API filter both use `changed_within=24`; the
  "changed since" filter with an explicit timestamp gives the right answer,
  they say.
- They saw it once and later in the morning it was "right again".

## Asks

1. Reproduce it, ideally as a test with the clock frozen at the reported
   time (`frozen_clock` in `tests/conftest.py`).
2. Fix it so "last 24h" means the last 24 elapsed hours for every org,
   whatever the DST situation, in the dashboard, the API and anything else
   that uses the same window.
3. Check the other side of the year: what happens on the day clocks go
   forward (Orchid, Pacific/Auckland)?
4. A two-line explanation I can send to the customer.
