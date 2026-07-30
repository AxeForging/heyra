"""Run with: pytest addons/heyra/ -- regression guard for the real 502 bug this
fixes (uvicorn binding to a hardcoded fallback port instead of the real
Supervisor-assigned dynamic ingress port)."""
from unittest.mock import Mock, patch

from run import DEFAULT_INGRESS_PORT, get_ingress_port


def test_no_supervisor_token_falls_back_to_default(monkeypatch):
    monkeypatch.delenv("SUPERVISOR_TOKEN", raising=False)
    assert get_ingress_port() == DEFAULT_INGRESS_PORT


def test_fetches_real_ingress_port_from_supervisor_api(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    fake_response = Mock()
    fake_response.json.return_value = {"data": {"ingress_port": 63412}}
    with patch("run.requests.get", return_value=fake_response) as mock_get:
        assert get_ingress_port() == 63412
    args, kwargs = mock_get.call_args
    assert args[0] == "http://supervisor/addons/self/info"
    assert kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_supervisor_api_failure_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("SUPERVISOR_TOKEN", "test-token")
    with patch("run.requests.get", side_effect=ConnectionError("no route to host")):
        assert get_ingress_port() == DEFAULT_INGRESS_PORT
