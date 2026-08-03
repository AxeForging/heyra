"""Run with: pytest addons/heyra/ (needs starlette installed)."""
from unittest.mock import Mock, patch

from app.main import (
    FLASH_URL,
    STATUS_HTML,
    assign,
    fetch_device_unit_id,
    fetch_unit_snapshot,
    next_unit_id,
    render_discovered_html,
    render_units_html,
)


class _FakeRequest:
    """Just enough of Starlette's Request to drive assign() without a real ASGI call."""

    def __init__(self, form_data):
        self._form_data = form_data

    async def form(self):
        return self._form_data


def test_next_unit_id_starts_at_one_when_no_units_configured():
    assert next_unit_id({}) == 1


def test_next_unit_id_skips_used_ids():
    assert next_unit_id({"1": {}, "2": {}}) == 3


def test_next_unit_id_fills_a_gap():
    assert next_unit_id({"1": {}, "3": {}}) == 2


def test_render_units_html_empty_shows_starting_up_message():
    assert "starting up" in render_units_html({})


def test_render_units_html_shows_room_and_online_status():
    rendered = render_units_html({"1": {"room": "kitchen", "online": True, "last_packet_age_s": 1.2}})
    assert "kitchen" in rendered
    assert "pill-online" in rendered
    assert "1s ago" in rendered


def test_render_units_html_escapes_room_name():
    rendered = render_units_html({"1": {"room": "<script>", "online": False, "last_packet_age_s": None}})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_fetch_unit_snapshot_returns_json_on_success():
    fake_response = Mock()
    fake_response.json.return_value = {"status": "ok", "units": {}}
    with patch("app.main.requests.get", return_value=fake_response):
        assert fetch_unit_snapshot() == {"status": "ok", "units": {}}


def test_fetch_unit_snapshot_returns_empty_dict_on_failure():
    with patch("app.main.requests.get", side_effect=ConnectionError("listener not up yet")):
        assert fetch_unit_snapshot() == {}


def test_status_html_renders_flash_link_and_units():
    rendered = STATUS_HTML.format(
        units_html=render_units_html({"1": {"room": "kitchen", "online": True, "last_packet_age_s": 1.2}}),
        discovered_html="",
        next_unit_id=next_unit_id({"1": {}}),
        flash_url=FLASH_URL,
    )
    assert FLASH_URL in rendered
    assert "kitchen" in rendered
    assert "next available unit ID: 2" in rendered


def test_fetch_device_unit_id_returns_value_on_success():
    fake_response = Mock()
    fake_response.json.return_value = {"id": "number-unit_id", "value": 3, "state": "3"}
    with patch("app.main.requests.get", return_value=fake_response):
        assert fetch_device_unit_id("heyra-atom-echo-a1b2c3.local") == 3


def test_fetch_device_unit_id_returns_none_on_failure():
    with patch("app.main.requests.get", side_effect=ConnectionError("device not reachable")):
        assert fetch_device_unit_id("heyra-atom-echo-a1b2c3.local") is None


async def test_render_discovered_html_empty_when_no_devices():
    rendered = await render_discovered_html({}, [1, 2])
    assert "No unclaimed devices found yet" in rendered


async def test_render_discovered_html_shows_hostname_and_assign_form():
    fake_response = Mock()
    fake_response.json.return_value = {"value": 1}
    with patch("app.main.requests.get", return_value=fake_response):
        rendered = await render_discovered_html({"heyra-atom-echo-a1b2c3.local": object()}, [1, 2])
    assert "heyra-atom-echo-a1b2c3.local" in rendered
    assert "currently reports unit 1" in rendered
    assert 'action="assign"' in rendered
    assert '<option value="2">2</option>' in rendered


async def test_render_discovered_html_shows_not_reachable_on_failure():
    with patch("app.main.requests.get", side_effect=ConnectionError("not up yet")):
        rendered = await render_discovered_html({"heyra-atom-echo-a1b2c3.local": object()}, [1])
    assert "not reachable yet" in rendered


async def test_assign_redirects_relative_not_absolute():
    # A "/" redirect drops HA Ingress's path prefix and re-loads the whole HA frontend
    # (sidebar included) inside the panel's own iframe -- already happened once for
    # /flash (bd4a684). Pin this down so it can't silently regress here too.
    with patch("app.main.requests.post"):
        response = await assign(_FakeRequest({"hostname": "heyra-atom-echo-a1b2c3.local", "unit_id": "1"}))
    assert response.status_code == 303
    assert response.headers["location"] == "."
