import json
import urllib.error
import unittest
from unittest.mock import patch

from agent_code import skill_manager as sm


class SkillStoreAuthFlowTests(unittest.TestCase):
    def _http_error(self, code, payload):
        return urllib.error.HTTPError(
            "https://skills-manager.freesrv.com/login", code,
            "error", {}, __import__("io").BytesIO(payload.encode("utf-8")))

    def test_bad_login_is_not_reported_as_expired_session(self):
        with patch.object(sm.urllib.request, "urlopen", side_effect=self._http_error(
                401, json.dumps({"error": "invalid nickname or password"}))):
            with self.assertRaises(sm.ApiError) as ctx:
                sm._do_request(sm.SKILL_SERVER_PRIMARY, "POST", "/login", {},
                               {"nickname": "alice", "password": "wrong"}, False)
        self.assertNotIn("AUTH_EXPIRED", str(ctx.exception))
        self.assertIn("invalid nickname", str(ctx.exception))

    def test_authenticated_401_is_reported_as_expired_session(self):
        with patch.object(sm.urllib.request, "urlopen", side_effect=self._http_error(
                401, json.dumps({"error": "not authenticated"}))):
            with self.assertRaises(sm.ApiError) as ctx:
                sm._do_request(sm.SKILL_SERVER_PRIMARY, "GET", "/me", {"token": "test-token"}, None, True)
        self.assertIn("AUTH_EXPIRED", str(ctx.exception))

    def test_plaintext_http_fallback_is_not_configured(self):
        self.assertEqual(sm.SKILL_SERVERS, [sm.SKILL_SERVER_PRIMARY])
        self.assertTrue(sm.SKILL_SERVER_PRIMARY.startswith("https://"))

    def test_server_rejection_does_not_trigger_automatic_registration(self):
        import inspect
        source = inspect.getsource(sm.LoginDialog._submit)
        self.assertIn('endpoint = "/register" if mode == "register" else "/login"', source)
        self.assertNotIn('api("POST", "/register"', source)


if __name__ == "__main__":
    unittest.main()
