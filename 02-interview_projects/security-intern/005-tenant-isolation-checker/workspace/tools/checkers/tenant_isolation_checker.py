"""AST checker for multi-tenant query scoping in Bellpost.

Inspects Python source files for database queries on multi-tenant models
(such as Ticket, Attachment, User) to verify that queries are scoped by
tenant_id or tenant context.

Flags unscoped queries like:
    Ticket.query.filter_by(id=ticket_id).first()
    session.query(Ticket).filter(Ticket.id == ticket_id).first()

Supports exempting system background workers and infrastructure tasks that
legitimately operate across tenant boundaries.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import pathlib
import sys
from typing import Any

# Default list of multi-tenant models that require tenant scoping
TENANT_SCOPED_MODELS: frozenset[str] = frozenset({
    "Ticket",
    "Attachment",
    "User",
    "ApiToken",
    "AuditLog",
    "WebhookDelivery",
    "IngestReceipt",
})

# Default path substrings or filenames exempt from tenant scoping checks
DEFAULT_EXEMPT_PATHS: tuple[str, ...] = (
    "app/webhooks/",
    "app/ingest/",
    "app/legacy/",
    "tools/",
    "tests/",
    "seed/",
    "migrations/",
)


class TenantQueryVisitor(ast.NodeVisitor):
    """AST visitor that checks for unscoped model queries."""

    def __init__(self, filename: str) -> None:
        self.filename: str = filename
        self.violations: list[dict[str, Any]] = []

    def _is_tenant_scoped_call(self, node: ast.Call) -> bool:
        """Check if a query call chain contains tenant_id or tenant scoping."""
        for keyword in node.keywords:
            if keyword.arg in ("tenant_id", "tenant"):
                return True
        for arg in node.args:
            arg_str = ast.dump(arg)
            if "tenant_id" in arg_str or "tenant" in arg_str:
                return True
        return False

    def _find_query_model(self, node: ast.AST) -> str | None:
        """Check if an AST node represents a query against a tenant model."""
        if not isinstance(node, ast.Call):
            return None

        # Case 1: session.query(Model)
        if isinstance(node.func, ast.Attribute) and node.func.attr == "query":
            for arg in node.args:
                if isinstance(arg, ast.Name) and arg.id in TENANT_SCOPED_MODELS:
                    return arg.id

        # Case 2: Model.query or Model.query.filter_by(...)
        curr: ast.AST = node
        while isinstance(curr, ast.Call):
            if isinstance(curr.func, ast.Attribute):
                if curr.func.attr == "query" and isinstance(curr.func.value, ast.Name):
                    if curr.func.value.id in TENANT_SCOPED_MODELS:
                        return curr.func.value.id
                curr = curr.func.value
            else:
                break
        if isinstance(curr, ast.Attribute) and curr.attr == "query":
            if isinstance(curr.value, ast.Name) and curr.value.id in TENANT_SCOPED_MODELS:
                return curr.value.id

        return None

    def visit_Call(self, node: ast.Call) -> None:
        """Inspect function and method calls for queries on multi-tenant models."""
        func_name = ""
        if isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        # Only evaluate at chain terminal or filter calls
        if func_name in ("first", "all", "one", "one_or_none", "count", "filter", "filter_by"):
            target_model: str | None = None
            has_tenant_scope = False

            # Walk through the whole call chain
            curr: ast.AST = node
            while isinstance(curr, ast.Call):
                model = self._find_query_model(curr)
                if model is not None:
                    target_model = model

                if self._is_tenant_scoped_call(curr):
                    has_tenant_scope = True

                if isinstance(curr.func, ast.Attribute):
                    curr = curr.func.value
                else:
                    break

            if target_model is not None and has_tenant_scope is False:
                violation = {
                    "file": self.filename,
                    "line": node.lineno,
                    "col": node.col_offset,
                    "model": target_model,
                    "message": f"Unscoped query on multi-tenant model '{target_model}' missing tenant scoping filter.",
                }
                if not any(v["line"] == node.lineno and v["file"] == self.filename for v in self.violations):
                    self.violations.append(violation)

        self.generic_visit(node)


def is_path_exempt(file_path: str, exemptions: list[str]) -> bool:
    """Return True if the file path matches any exemption pattern."""
    normalized = file_path.replace("\\", "/")
    for pattern in exemptions:
        if pattern in normalized or normalized.endswith(pattern):
            return True
    return False


def check_file(file_path: pathlib.Path, exemptions: list[str] | None = None) -> list[dict[str, Any]]:
    """Parse and check a single Python file for unscoped tenant queries."""
    if exemptions is None:
        exemptions = list(DEFAULT_EXEMPT_PATHS)

    path_str = str(file_path)
    if is_path_exempt(path_str, exemptions):
        return []

    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return []

    # Check for file-level exemption comment
    if "# tenant-exemption" in content or "# tenant-exempt" in content:
        return []

    try:
        tree = ast.parse(content, filename=path_str)
    except SyntaxError as err:
        return [{
            "file": path_str,
            "line": err.lineno or 1,
            "col": err.offset or 0,
            "model": "SyntaxError",
            "message": f"Failed to parse AST: {err}",
        }]

    visitor = TenantQueryVisitor(filename=path_str)
    visitor.visit(tree)
    return visitor.violations


def scan_directory(
    root_path: pathlib.Path,
    exemptions: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Recursively scan Python files in a directory."""
    violations: list[dict[str, Any]] = []
    if root_path.is_file():
        return check_file(root_path, exemptions)

    for py_file in sorted(root_path.rglob("*.py")):
        # Skip hidden files
        if any(part.startswith(".") for part in py_file.parts):
            continue
        file_violations = check_file(py_file, exemptions)
        violations.extend(file_violations)

    return violations


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for tenant isolation checker."""
    parser = argparse.ArgumentParser(
        description="Verify multi-tenant query scoping in Python source files."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="app",
        help="Target file or directory to scan (default: app)",
    )
    parser.add_argument(
        "--exempt",
        action="append",
        default=[],
        help="Path substring or filename pattern to exempt from scanning",
    )
    parser.add_argument(
        "--no-default-exemptions",
        action="store_true",
        help="Disable built-in exemption rules for workers and tools",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )

    args = parser.parse_args(argv)
    target_path = pathlib.Path(args.target)

    if not target_path.exists():
        print(f"Error: Target path does not exist: {target_path}", file=sys.stderr)
        return 2

    exemptions = list(args.exempt)
    if not args.no_default_exemptions:
        exemptions.extend(DEFAULT_EXEMPT_PATHS)

    violations = scan_directory(target_path, exemptions=exemptions)

    if args.json:
        print(json.dumps(violations, indent=2))
    else:
        if len(violations) == 0:
            print(f"PASS: No unscoped multi-tenant queries found in {target_path}.")
        else:
            print(f"FAIL: Found {len(violations)} unscoped multi-tenant queries:\n")
            for v in violations:
                print(f"  {v['file']}:{v['line']}:{v['col']} - {v['message']}")

    return 1 if len(violations) > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
