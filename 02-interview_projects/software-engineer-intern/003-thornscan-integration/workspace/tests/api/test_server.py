import http.client
import json
import threading
from dataclasses import replace
from datetime import timedelta

from ledger.api.server import make_server
from ledger.core import repo
from ledger.core.models import Location, Severity, Status, Triage
from tests.helpers import TODAY, LedgerTestCase, make_finding, make_repo, make_run, make_team, sarif_report

READ = "DEMO-ldg-ro-7f3a9c21e5b84d60"
ADMIN = "DEMO-ldg-admin-2c8e41b7a9d05f36"
REPORT = sarif_report(("src/payments/refunds.py", 42), ("src/payments/webhooks.py", 63))
TRUNCATED = b'{"version": "2.1.0", "runs": [\n  {"tool": {"driver": {"name": "Brackish"}},\n  "results": [,'


class ApiTestCase(LedgerTestCase):
    def setUp(self):
        super().setUp()
        self.start(self.settings)
        self.team = make_team(self.conn, "payments")
        self.repo = make_repo(self.conn, "checkout-api", team=self.team)
        self.run = make_run(self.conn, self.repo)

    def start(self, settings):
        server = make_server(settings, host="127.0.0.1", port=0)
        threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        self.port = server.server_address[1]

    def call(self, method, path, *, token=READ, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        self.addCleanup(conn.close)
        headers = dict(headers or {})
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        conn.request(method, path, body=body, headers=headers)
        response = conn.getresponse()
        return response.status, json.loads(response.read()), response


class RoutingAndAuthTest(ApiTestCase):
    def test_health_needs_no_token(self):
        status, body, response = self.call("GET", "/api/v1/health", token=None)
        self.assertEqual(status, 200)
        self.assertEqual((body["status"], body["version"], body["schema_version"]), ("ok", "2.4.1", 1))
        self.assertEqual(response.getheader("Content-Type"), "application/json; charset=utf-8")

    def test_missing_unknown_and_malformed_tokens_are_401(self):
        for token, header in ((None, None), ("DEMO-ldg-ro-0000000000000000", None), (None, f"Basic {READ}")):
            status, body, response = self.call("GET", "/api/v1/findings", token=token, headers={"Authorization": header} if header else None)
            self.assertEqual((status, body["error"]), (401, "unauthorized"))
            self.assertIn("Bearer", response.getheader("WWW-Authenticate"))

    def test_read_token_cannot_call_admin_endpoints(self):
        finding = make_finding(self.conn, self.run)
        status, body, _ = self.call("POST", f"/api/v1/findings/{finding.id}/triage", body={"triage": "confirmed"})
        self.assertEqual((status, body["error"]), (403, "forbidden"))
        self.assertEqual(repo.get_finding(self.conn, finding.id).triage, Triage.UNTRIAGED)

    def test_unknown_route_wrong_method_and_trailing_slash(self):
        self.assertEqual(self.call("GET", "/api/v1/nope")[0], 404)
        self.assertEqual(self.call("GET", "/api/v1/findings/abc")[0], 404)
        status, body, response = self.call("DELETE", "/api/v1/findings")
        self.assertEqual((status, body["error"], response.getheader("Allow")), (405, "method_not_allowed", "GET"))
        self.assertEqual(self.call("GET", "/api/v1/findings/?limit=1")[0], 200)


class FindingsTest(ApiTestCase):
    def test_filters_order_and_pagination(self):
        other = make_repo(self.conn, "route-planner", team=make_team(self.conn, "routing"))
        low = make_finding(self.conn, self.run, severity=Severity.LOW)
        crit = make_finding(self.conn, self.run, severity=Severity.CRITICAL)
        high = make_finding(self.conn, self.run, severity=Severity.HIGH, status=Status.FIXED)
        crit2 = make_finding(self.conn, make_run(self.conn, other), severity=Severity.CRITICAL)
        hidden = make_finding(self.conn, self.run, severity=Severity.CRITICAL, suppressed=True)

        status, body, _ = self.call("GET", "/api/v1/findings")
        self.assertEqual(status, 200)
        self.assertEqual([i["id"] for i in body["items"]], [crit.id, crit2.id, high.id, low.id])
        self.assertEqual((body["total"], body["limit"], body["offset"]), (4, 50, 0))
        self.assertEqual(body["items"][0]["repo"], "checkout-api")
        self.assertEqual(body["items"][0]["location"]["kind"], "code")

        _, body, _ = self.call("GET", "/api/v1/findings?severity=critical&severity=low&team=payments")
        self.assertEqual([i["id"] for i in body["items"]], [crit.id, low.id])
        _, body, _ = self.call("GET", "/api/v1/findings?repo=checkout-api&status=fixed")
        self.assertEqual([i["id"] for i in body["items"]], [high.id])
        _, body, _ = self.call("GET", "/api/v1/findings?suppressed=true")
        self.assertEqual([i["id"] for i in body["items"]], [hidden.id])
        _, body, _ = self.call("GET", "/api/v1/findings?limit=2&offset=1")
        self.assertEqual(([i["id"] for i in body["items"]], body["total"]), ([crit2.id, high.id], 4))

    def test_invalid_query_parameters_are_400(self):
        for query in ("limit=0", "limit=201", "limit=x", "offset=-1", "severity=urgent", "suppressed=yes",
                      "sevrity=high", "limit=1&limit=2"):
            status, body, _ = self.call("GET", f"/api/v1/findings?{query}")
            self.assertEqual((status, body["error"]), (400, "invalid_input"), query)

    def test_detail_has_occurrences_and_events(self):
        finding = make_finding(self.conn, self.run, location=Location.code("src/refunds.py", 42, 9))
        repo.insert(self.conn, "occurrences", {
            "finding_id": finding.id, "run_id": self.run.id, "tool": "brackish", "rule_id": finding.rule_id,
            "tool_severity": "warning", "raw_location": "./src/refunds.py:42:9", "message": finding.message,
        })
        repo.add_event(self.conn, finding.id, "new", run_id=self.run.id, to_value="new")
        status, body, _ = self.call("GET", f"/api/v1/findings/{finding.id}")
        self.assertEqual((status, body["id"], body["repo"]), (200, finding.id, "checkout-api"))
        self.assertEqual(body["occurrences"][0]["raw_location"], "./src/refunds.py:42:9")
        self.assertEqual(body["occurrences"][0]["commit_sha"], self.run.commit_sha)
        self.assertEqual([e["kind"] for e in body["events"]], ["new"])
        self.assertEqual(self.call("GET", "/api/v1/findings/999999")[:2][0], 404)

    def test_triage_records_event_with_token_name(self):
        finding = make_finding(self.conn, self.run)
        body = {"triage": "accepted_risk", "note": "WAF rule, SEC-311"}
        status, result, _ = self.call("POST", f"/api/v1/findings/{finding.id}/triage", token=ADMIN, body=body)
        self.assertEqual((status, result["triage"], result["triaged_by"]), (200, "accepted_risk", "appsec-admin"))
        self.assertEqual(result["triaged_at"], "2026-09-23T12:00:00Z")
        event = repo.finding_events(self.conn, finding.id)[-1]
        self.assertEqual((event.kind, event.from_value, event.to_value, event.actor, event.note),
                         ("triage", "untriaged", "accepted_risk", "appsec-admin", "WAF rule, SEC-311"))

    def test_triage_rejects_bad_bodies(self):
        finding = make_finding(self.conn, self.run)
        path = f"/api/v1/findings/{finding.id}/triage"
        for body in (b"{not json", {"triage": "wontfix"}, {"note": "x"}, ["confirmed"], {"triage": "confirmed", "note": 5}):
            self.assertEqual(self.call("POST", path, token=ADMIN, body=body)[0], 400, body)
        self.assertEqual(self.call("POST", "/api/v1/findings/999999/triage", token=ADMIN, body={"triage": "confirmed"})[0], 404)
        self.assertEqual(repo.finding_events(self.conn, finding.id), [])


class IngestAndTeamsTest(ApiTestCase):
    """The real ingest pipeline and SLA breach query behind the endpoints."""

    def ingest(self, query, body=REPORT, token=ADMIN):
        return self.call("POST", f"/api/v1/ingest?{query}", token=token, body=body)

    def runs(self):
        return repo.fetch_one(self.conn, "SELECT COUNT(*) FROM runs")[0]

    def test_ingest_raw_body_with_query_metadata(self):
        status, body, _ = self.ingest("repo=checkout-api&branch=main&commit=4be1f0c9d2&source=brackish.sarif")
        self.assertEqual((status, body["repo"], body["tool"], body["raw_count"], body["new_count"]),
                         (201, "checkout-api", "brackish", 2, 2))
        run = repo.get_run(self.conn, body["run_id"])
        self.assertEqual((run.commit_sha, run.source_name, run.new_count), ("4be1f0c9d2", "brackish.sarif", 2))
        status, body, _ = self.ingest("repo=checkout-api&branch=main&commit=4be1f0c9d2&source=brackish.sarif")
        self.assertEqual((status, body["error"]), (409, "conflict"))

    def test_ingest_errors(self):
        before = self.runs()
        self.assertEqual(self.ingest("repo=checkout-api&branch=main&commit=abc1234", token=READ)[0], 403)
        status, body, _ = self.ingest("repo=checkout-api&branch=main")
        self.assertEqual((status, body["missing"]), (400, ["commit"]))
        self.assertEqual(self.ingest("repo=nope&branch=main&commit=abc1234")[0], 404)
        self.assertEqual(self.ingest("repo=checkout-api&branch=main&commit=abc1234", body=b"")[0], 400)
        self.assertEqual(self.ingest("repo=checkout-api&branch=main&commit=release-1")[0], 400)
        status, body, _ = self.ingest("repo=checkout-api&branch=main&commit=abc1234&source=x.sarif", body=TRUNCATED)
        self.assertEqual((status, body["error"], body["line"]), (422, "parse_error", 3))
        status, body, _ = self.ingest("repo=checkout-api&branch=main&commit=abc1234", body=b"<html></html>")
        self.assertEqual((status, body["error"]), (415, "unknown_format"))
        self.assertEqual(self.runs(), before)  # nothing written by a rejected upload

    def test_ingest_above_upload_limit_is_413(self):
        self.start(replace(self.settings, max_upload_bytes=64))
        status, body, _ = self.ingest("repo=checkout-api&branch=main&commit=abc1234", body=b"x" * 65)
        self.assertEqual((status, body["error"], body["limit"]), (413, "payload_too_large", 64))

    def test_team_summary(self):
        routing = make_team(self.conn, "routing")
        overdue = TODAY - timedelta(days=3)
        make_finding(self.conn, self.run, severity=Severity.CRITICAL, due_at=overdue)
        make_finding(self.conn, self.run, severity=Severity.CRITICAL, status=Status.REOPENED)
        make_finding(self.conn, self.run, severity=Severity.HIGH, status=Status.FIXED, due_at=overdue)
        make_finding(self.conn, self.run, severity=Severity.HIGH, suppressed=True, due_at=overdue)
        make_finding(self.conn, self.run, severity=Severity.LOW, triage=Triage.FALSE_POSITIVE, due_at=overdue)
        status, body, _ = self.call("GET", "/api/v1/teams")
        self.assertEqual(status, 200)
        payments, routing_item = body["items"]
        self.assertEqual(payments["open"], {"critical": 2, "high": 0, "medium": 0, "low": 0, "info": 0})
        self.assertEqual((payments["slug"], payments["open_total"], payments["breaches"]), ("payments", 2, 1))
        self.assertEqual((routing_item["id"], routing_item["open_total"], routing_item["breaches"]), (routing.id, 0, 0))
