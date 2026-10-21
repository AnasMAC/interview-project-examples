import unittest
from unittest import mock

from ledger.api import auth
from ledger.api.router import MethodNotAllowed, Router
from ledger.core.config import ApiToken
from ledger.core.errors import Forbidden, NotFound, Unauthorized

TOKENS = (ApiToken("dashboard-ro", "read", "r" * 24), ApiToken("appsec-admin", "admin", "a" * 24))


class RouterTest(unittest.TestCase):
    def setUp(self):
        self.router = Router()
        self.router.add("GET", "/api/v1/findings/{id:int}", "detail", role="read")
        self.router.add("POST", "/api/v1/findings/{id:int}/triage", "triage", role="admin")
        self.router.add("GET", "/api/v1/repos/{name}", "repo", role="read")

    def test_params_are_converted(self):
        route, params = self.router.resolve("GET", "/api/v1/findings/42/")
        self.assertEqual((route.handler, params), ("detail", {"id": 42}))
        self.assertEqual(self.router.resolve("get", "/api/v1/repos/checkout-api")[1], {"name": "checkout-api"})

    def test_404_and_405(self):
        for path in ("/api/v1/findings/x", "/api/v1/findings/1/2", "/api/v1/repos/a/b", "/"):
            with self.assertRaises(NotFound):
                self.router.resolve("GET", path)
        with self.assertRaises(MethodNotAllowed) as caught:
            self.router.resolve("GET", "/api/v1/findings/7/triage")
        self.assertEqual(caught.exception.details["allowed"], ["POST"])


class AuthTest(unittest.TestCase):
    def test_bearer_lookup(self):
        self.assertEqual(auth.authenticate("Bearer " + "a" * 24, TOKENS).name, "appsec-admin")
        self.assertEqual(auth.authenticate("bearer  " + "r" * 24 + " ", TOKENS).name, "dashboard-ro")
        for header in (None, "", "Bearer", "Bearer " + "r" * 23, "Token " + "r" * 24, "Bearer " + "r" * 25):
            with self.assertRaises(Unauthorized):
                auth.authenticate(header, TOKENS)

    def test_every_token_is_compared(self):
        with mock.patch.object(auth.hmac, "compare_digest", wraps=auth.hmac.compare_digest) as compare:
            auth.authenticate("Bearer " + "r" * 24, TOKENS)
        self.assertEqual(compare.call_count, len(TOKENS))

    def test_roles(self):
        reader, admin = TOKENS
        auth.require(reader, "read")
        auth.require(admin, "read")
        auth.require(admin, "admin")
        with self.assertRaises(Forbidden):
            auth.require(reader, "admin")
