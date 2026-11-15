import json

from fastapi.testclient import TestClient

from torquespec import knowledge
from torquespec.app import create_app
from torquespec.diagnose import Diagnoser


class FakeDiagnoser(Diagnoser):
    def __init__(self, available=True):
        super().__init__(knowledge.load(), client=None)
        self._available = available
        self.seen = None

    @property
    def available(self):
        return self._available

    async def stream(self, turns):
        self.seen = turns
        for chunk in ["Check the ", "ISC valve."]:
            yield chunk


def client(diag=None):
    return TestClient(create_app(diag or FakeDiagnoser()))


def test_index_and_health():
    c = client()
    assert "Torque Spec" in c.get("/").text
    assert c.get("/api/health").json() == {"ok": True, "llm": True}


def test_reference_endpoints():
    c = client()
    rows = c.get("/api/torque", params={"q": "drain"}).json()
    assert rows[0]["component"] == "Oil drain plug" and "N·m" in rows[0]["nm"]
    assert c.get("/api/codes/34").json()["code"] == "34"
    assert c.get("/api/codes/77").status_code == 404
    assert len(c.get("/api/issues").json()) >= 5


def test_diagnose_streams_sse():
    diag = FakeDiagnoser()
    r = client(diag).post("/api/diagnose", json={"messages": [{"role": "user", "content": "rough idle"}]})
    assert r.status_code == 200
    events = [e.removeprefix("data: ") for e in r.text.strip().split("\n\n")]
    assert events[-1] == "[DONE]"
    assert "".join(json.loads(e)["text"] for e in events[:-1]) == "Check the ISC valve."
    assert diag.seen[0].content == "rough idle"


def test_diagnose_validates_conversation():
    c = client()
    bad = [
        {"messages": []},
        {"messages": [{"role": "assistant", "content": "hi"}]},
        {"messages": [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]},
        {"messages": [{"role": "system", "content": "x"}]},
    ]
    for body in bad:
        assert c.post("/api/diagnose", json=body).status_code == 422


def test_diagnose_without_key_returns_503():
    r = client(FakeDiagnoser(available=False)).post(
        "/api/diagnose", json={"messages": [{"role": "user", "content": "no start"}]})
    assert r.status_code == 503
