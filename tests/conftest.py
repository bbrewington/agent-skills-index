import ghapi
import pytest


class Resp:
    def __init__(self, payload=None, status=200, text=""):
        self._payload = payload
        self.status_code = status
        self.text = text
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests

            raise requests.HTTPError(f"{self.status_code}")


class FakeGitHub:
    """Routes keyed by API path. A value may be a payload, a Resp, or a callable(params) -> either."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, path, params=None, accept=None):
        self.calls.append((path, params))
        if path not in self.routes:
            return Resp({}, 404)
        value = self.routes[path]
        if callable(value):
            value = value(params)
        return value if isinstance(value, Resp) else Resp(value)


@pytest.fixture
def gh(monkeypatch):
    def install(routes):
        fake = FakeGitHub(routes)
        monkeypatch.setattr(ghapi, "get", fake)
        return fake

    return install
