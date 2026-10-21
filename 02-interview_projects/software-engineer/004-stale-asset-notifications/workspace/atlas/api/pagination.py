"""Cursor pagination (since 0.9, ADR 0003).

Offsets got slow and skipped rows while imports kept updating
``last_seen_at``; a cursor stays stable. ``-id`` breaks ties between assets
seen in the same import, which share ``last_seen_at``.
"""

from rest_framework.pagination import CursorPagination


class AssetCursorPagination(CursorPagination):
    ordering = ("-last_seen_at", "-id")
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 500


class ChangeCursorPagination(AssetCursorPagination):
    ordering = ("-occurred_at", "-id")


class ExposureCursorPagination(AssetCursorPagination):
    ordering = ("-opened_at", "-id")
