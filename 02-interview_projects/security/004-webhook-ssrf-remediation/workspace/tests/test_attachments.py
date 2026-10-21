"""Attachments: policy, storage layout, download and collection.

Coverage plan: the streaming 10 MiB cap, the allowed-type list, the per-ticket
quota, ``storage_path`` layout and sanitizing, download headers (always
``Content-Disposition: attachment``), visibility for requesters, and the orphan
collector.
"""

from __future__ import annotations
