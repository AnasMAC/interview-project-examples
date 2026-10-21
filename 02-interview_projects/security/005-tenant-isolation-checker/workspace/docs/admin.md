# Agent console

Owner: Hannah Lindqvist. The console is server-rendered (Jinja templates under
`app/admin/templates/admin/`) and lives under `/admin`.

## Pages

| Path | What it does |
| --- | --- |
| `/admin/login`, `/admin/logout` | Session sign-in and sign-out |
| `/admin/` | Dashboard: per-status counts |
| `/admin/tickets` | Ticket list with status and priority filters |
| `/admin/tickets/<id>` | Detail: conversation, reply, status change, assignment |
| `/admin/users` | User list, invitations, role changes (admin only) |
| `/admin/tenants/settings` | Name, timezone and plan of the signed-in tenant |
| `/admin/webhooks` | Webhook list, enable/disable, create |
| `/admin/reports` | Per-status and per-day counts |
| `/admin/activity` | Audit log; **times are shown in UTC** with a visible label |
| `/admin/search` | Classic search (deprecated; kept for the mobile app) |

## Rules

* Every state-changing request carries `csrf_token` (form field) and is
  rejected without it.
* Role changes require the `admin` role; the target user is always loaded with
  the session's tenant filter.
* Pages render the tenant timezone except the Activity page, which renders UTC.
* Ticket bodies are rendered as text: the console never renders the HTML part
  of an email and never marks template output as safe.
