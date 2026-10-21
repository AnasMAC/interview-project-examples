# REQ-0219: Dashboard is slow for Quillstone's 40k assets

| | |
|---|---|
| From | Freya Lindqvist (product), with Omar Haddad (customer success) |
| Date | 2026-10-28 |
| Customer | Quillstone Media (`quillstone-media`) |
| Priority | High; Quillstone renews in January and mentioned it in the QBR |
| Status | Needs investigation |

## Customer report

> Since our CMS started registering every campaign microsite, Atlas has
> become painful. The asset list takes several seconds per page, filtering
> by tag is worse, and the CSV download of all hosts either takes minutes or
> our proxy cuts it off at 30 seconds. The API search with `q=` is slow too.
> -- Quillstone web platform team, via Omar

## What we know

- Quillstone has about 40,000 assets, mostly hosts under
  `campaigns.quillstone-media.example.test` plus their IPs and certificates,
  and grows by a few hundred a week. Harborview has a quarter of that.
- `make seed SEED_ARGS="--reset --scale 8"` gives a database of that shape
  (Quillstone ~40k assets, ~230k changes over all orgs) in about a minute.
  `make bench` times the asset search, the list page and the CSV download per
  org through Django's test client and prints query counts.
- Rafael thinks the list page does "a few queries per row" somewhere; nobody
  has measured.
- Some of their users open the list with five or six filters at once from
  saved views.

## Asks

1. Measure first: which pages and API calls are slow at this size, and why
   (queries, missing indexes, work done in Python). Put the before/after
   numbers from `make bench` in the PR.
2. Fix what you find without changing what the pages and API return:
   same filters, same columns, same order.
3. The CSV download should start streaming within a second and must not hold
   the whole result in memory.
4. If something cannot be fixed cheaply, write down the options and their
   cost instead of building them.

## Targets

| Page / call | Target at --scale 8 |
|---|---|
| Asset list, any filter combination | median under 300 ms |
| `GET /api/v1/assets/` (first page, filtered, deep cursor) | median under 200 ms |
| CSV download | first bytes under 1 s, constant memory |
