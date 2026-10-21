"""Operator commands. Each command is one transaction; the actor in audit
events is ``cli:<os user>``. Keys and callback secrets are printed once and
never stored in clear.
"""

from __future__ import annotations

import argparse
import getpass
import json
import re
import secrets
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Connection, insert, select

from gatekeeper.core import auth, clock
from gatekeeper.core.config import get_settings
from gatekeeper.core.db import transaction
from gatekeeper.core.errors import ApiError
from gatekeeper.core.logging import configure_logging
from gatekeeper.core.tables import api_keys, callback_outbox, services, teams

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class CliError(Exception):
    pass


def actor() -> str:
    return f"cli:{getpass.getuser()}"


def _record(conn: Connection, **kw) -> None:
    from gatekeeper.audit.service import record

    record(conn, actor=actor(), **kw)


def _slug(value: str) -> str:
    if not SLUG.match(value):
        raise argparse.ArgumentTypeError(f"{value!r} is not a slug ([a-z0-9-], 2-64 chars)")
    return value


def _team(conn: Connection, slug: str):
    row = conn.execute(select(teams).where(teams.c.slug == slug)).first()
    if row is None:
        raise CliError(f"team {slug!r} not found")
    return row


def create_team(conn: Connection, args: argparse.Namespace) -> str:
    try:
        ZoneInfo(args.timezone)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise CliError(f"unknown timezone {args.timezone!r}") from exc
    if conn.execute(select(teams.c.id).where(teams.c.slug == args.slug)).first():
        raise CliError(f"team {args.slug!r} already exists")
    secret = f"DEMO-whsec-{args.slug}-{secrets.token_hex(6)}"
    team_id = conn.execute(
        insert(teams).values(slug=args.slug, name=args.name, timezone=args.timezone,
                             callback_secret=secret, notify_url=args.notify_url,
                             created_at=clock.now()).returning(teams.c.id)
    ).scalar_one()
    _record(conn, action="team.created", subject_type="team", subject_id=team_id,
            team_id=team_id, details={"name": args.name})
    return f"team {args.slug} created (id {team_id})\ncallback secret (shown once): {secret}"


def create_service(conn: Connection, args: argparse.Namespace) -> str:
    team = _team(conn, args.team)
    exists = select(services.c.id).where(services.c.team_id == team.id,
                                         services.c.slug == args.slug)
    if conn.execute(exists).first():
        raise CliError(f"service {args.slug!r} already exists in {args.team}")
    name = args.name or args.slug.replace("-", " ").title()
    service_id = conn.execute(
        insert(services).values(team_id=team.id, slug=args.slug, name=name,
                                created_at=clock.now()).returning(services.c.id)
    ).scalar_one()
    return f"service {args.team}/{args.slug} created (id {service_id})"


def issue_key(conn: Connection, args: argparse.Namespace) -> str:
    team_id = _team(conn, args.team).id if args.team else None
    role = auth.ROLE_TEAM if args.team else auth.ROLE_REVIEWER
    live = select(api_keys.c.id).where(api_keys.c.name == args.name,
                                       api_keys.c.revoked_at.is_(None))
    if conn.execute(live).first():
        raise CliError(f"a live key named {args.name!r} exists; revoke it first")
    key_id, key = auth.issue_key(conn, name=args.name, role=role, team_id=team_id)
    _record(conn, action="key.issued", subject_type="api_key", subject_id=key_id,
            team_id=team_id, details={"name": args.name, "role": role})
    return f"key {args.name} issued (id {key_id}, role {role})\n{key}"


def revoke_key(conn: Connection, args: argparse.Namespace) -> str:
    row = conn.execute(select(api_keys).where(api_keys.c.name == args.name,
                                              api_keys.c.revoked_at.is_(None))).first()
    if row is None or not auth.revoke_key(conn, row.id):
        raise CliError(f"no live key named {args.name!r}")
    _record(conn, action="key.revoked", subject_type="api_key", subject_id=row.id,
            team_id=row.team_id, details={"name": row.name, "role": row.role})
    return f"key {args.name} revoked (id {row.id})"


def import_policy(conn: Connection, args: argparse.Namespace) -> str:
    from gatekeeper.evaluation.service import publish_policy

    team = _team(conn, args.team)
    try:
        source = Path(args.file).read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read {args.file}: {exc.strerror}") from exc
    view = publish_policy(conn, team_id=team.id, source=source, actor=actor(),
                          comment=args.comment)
    return f"policy version {view['version']} published for {args.team}"


def replay_callback(conn: Connection, args: argparse.Namespace) -> str:
    from gatekeeper.callbacks.service import replay

    lines = []
    for outbox_id in args.ids:
        row = conn.execute(select(callback_outbox).where(callback_outbox.c.id == outbox_id)
                           .with_for_update()).first()
        if row is None:
            raise CliError(f"outbox row {outbox_id} not found")
        if row.status == "pending":
            raise CliError(f"outbox row {outbox_id} is already pending")
        if row.status == "delivered" and not args.force:
            raise CliError(f"outbox row {outbox_id} was delivered; pass --force to resend")
        replay(conn, outbox_id=outbox_id, actor=actor())
        lines.append(f"outbox row {outbox_id} ({row.event}, was {row.status}) queued again")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m gatekeeper.cli",
                                     description="Gatekeeper operator commands.")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create-team", help="create a team and its callback secret")
    p.add_argument("slug", type=_slug)
    p.add_argument("--name", required=True)
    p.add_argument("--timezone", default="Europe/London", help="IANA name")
    p.add_argument("--notify-url", help="where waiver.expiring notices go")
    p.set_defaults(handler=create_team)

    p = sub.add_parser("create-service", help="register a service CI can evaluate")
    p.add_argument("team")
    p.add_argument("slug", type=_slug)
    p.add_argument("--name")
    p.set_defaults(handler=create_service)

    p = sub.add_parser("issue-key", help="issue an API key (printed once)")
    p.add_argument("name", help="label shown in audit as key:<name>")
    scope = p.add_mutually_exclusive_group(required=True)
    scope.add_argument("--team", help="team key for this team slug")
    scope.add_argument("--reviewer", action="store_true", help="security_reviewer key")
    p.set_defaults(handler=issue_key)

    p = sub.add_parser("revoke-key", help="revoke the live key with this name")
    p.add_argument("name")
    p.set_defaults(handler=revoke_key)

    p = sub.add_parser("import-policy", help="publish a policy YAML file as a new version")
    p.add_argument("team")
    p.add_argument("file")
    p.add_argument("--comment")
    p.set_defaults(handler=import_policy)

    p = sub.add_parser("replay-callback", help="queue dead (or, with --force, delivered) "
                                               "outbox rows for delivery again")
    p.add_argument("ids", type=int, nargs="+", metavar="OUTBOX_ID")
    p.add_argument("--force", action="store_true", help="also resend delivered rows")
    p.set_defaults(handler=replay_callback)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format, "cli")
    try:
        with transaction() as conn:
            output = args.handler(conn, args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except ApiError as exc:
        print(f"error: {exc.code}: {exc.message}", file=sys.stderr)
        if exc.details:
            print(json.dumps(exc.details, indent=2, default=str), file=sys.stderr)
        return 1
    print(output)
    return 0
