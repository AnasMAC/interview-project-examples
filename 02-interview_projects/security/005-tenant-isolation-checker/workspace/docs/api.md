# Ticket API v1

Owner: Tomás Ferreira. Base path `/api/v1`; all timestamps are ISO 8601 UTC
with a `Z` suffix. Authenticate with `Authorization: Bearer <token>`.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/tickets` | Filters `status`, `priority`, `assignee_id`, `requester_id`; cursor pagination (`cursor`, `limit` up to 100) |
| POST | `/tickets` | Creates a ticket and its opening message |
| GET | `/tickets/<id>` | Ticket detail |
| PATCH | `/tickets/<id>` | Subject, priority |
| POST | `/tickets/<id>/status` | Status transition; 409 `invalid_transition` when not allowed |
| POST | `/tickets/<id>/assign` | Assign or unassign an agent |
| GET | `/tickets/<id>/messages` | Conversation, oldest first |
| POST | `/tickets/<id>/messages` | Reply |
| GET | `/tickets/<id>/attachments` | Attachment list |
| POST | `/tickets/<id>/attachments` | Multipart upload (10 MiB, allowed types only) |
| GET | `/attachments/<id>/download` | Always `Content-Disposition: attachment` |
| GET | `/me` | The identity behind the current token |
| GET | `/search` | Deprecated: capped at 200 rows, no pagination, kept for the mobile companion app 3.x line |

## Errors

```json
{"error": {"code": "not_found", "message": "not found"}}
```

Codes: `validation_failed` (422), `unauthenticated` (401), `not_found` (404),
`invalid_transition` (409), `file_too_large` (413), `quota_exceeded` (413),
`unsupported_media_type` (415), `internal_error` (500).

## Pagination

`GET /tickets` returns `{"items": [...], "next_cursor": "..."}`. The order is
`created_at DESC, id DESC` and `next_cursor` is opaque; pass it back unchanged.
There is no total count.
