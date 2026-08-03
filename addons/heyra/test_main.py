"""Run with: pytest addons/heyra/ (needs starlette installed)."""
from unittest.mock import AsyncMock, Mock, patch

from app.main import (
    FLASH_URL,
    STATUS_HTML,
    assign,
    fetch_device_unit_id,
    fetch_unit_snapshot,
    filter_sort_events,
    next_unit_id,
    render_discovered_html,
    render_events_html,
    render_units_html,
    rename,
    reraise,
    sanitize_room,
)


class _FakeRequest:
    """Just enough of Starlette's Request to drive a POST route without a real ASGI call."""

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
        events_html="",
        discovered_html="",
        next_unit_id=next_unit_id({"1": {}}),
        flash_url=FLASH_URL,
    )
    assert FLASH_URL in rendered
    assert "kitchen" in rendered
    assert "next available unit ID: 2" in rendered


def test_render_units_html_includes_rename_form():
    rendered = render_units_html({"1": {"room": "kitchen", "online": True, "last_packet_age_s": 1.2}})
    assert 'action="rename"' in rendered
    assert 'value="kitchen"' in rendered


def test_sanitize_room_lowercases_and_replaces_separators():
    assert sanitize_room("Living Room") == "living_room"
    assert sanitize_room("  Kitchen!! ") == "kitchen"


def test_sanitize_room_empty_for_no_valid_characters():
    assert sanitize_room("###") == ""


def test_filter_sort_events_filters_by_event_and_unit():
    events = [
        {"unit_id": 1, "room": "kitchen", "event": "baby_cry", "score": 0.9, "ts": 100},
        {"unit_id": 1, "room": "kitchen", "event": "smoke_alarm", "score": 0.8, "ts": 200},
        {"unit_id": 2, "room": "office", "event": "baby_cry", "score": 0.7, "ts": 150},
    ]
    result = filter_sort_events(events, "baby_cry", "1", "newest")
    assert len(result) == 1
    assert result[0]["ts"] == 100


def test_filter_sort_events_orders_newest_oldest_score():
    events = [
        {"unit_id": 1, "room": "kitchen", "event": "a", "score": 0.5, "ts": 100},
        {"unit_id": 1, "room": "kitchen", "event": "b", "score": 0.9, "ts": 300},
        {"unit_id": 1, "room": "kitchen", "event": "c", "score": 0.7, "ts": 200},
    ]
    assert [e["ts"] for e in filter_sort_events(events, "all", "all", "newest")] == [300, 200, 100]
    assert [e["ts"] for e in filter_sort_events(events, "all", "all", "oldest")] == [100, 200, 300]
    assert [e["score"] for e in filter_sort_events(events, "all", "all", "score")] == [0.9, 0.7, 0.5]


def test_render_events_html_empty_when_no_events():
    rendered = render_events_html([], {}, {})
    assert "No events yet" in rendered


def test_render_events_html_shows_reraise_form():
    events = [{"unit_id": 1, "room": "kitchen", "event": "baby_cry", "score": 0.9, "ts": 1700000000}]
    rendered = render_events_html(events, {"1": {"room": "kitchen"}}, {})
    assert "baby_cry" in rendered
    assert "kitchen" in rendered
    assert 'action="reraise"' in rendered
    assert "Raise alarm" in rendered


async def test_reraise_publishes_via_mqtt_and_redirects_relative():
    fake_snapshot = {"units": {"1": {"room": "kitchen"}}}
    with patch("app.main.fetch_unit_snapshot", return_value=fake_snapshot), \
         patch("app.main._mqtt_publish_once", new_callable=AsyncMock) as mock_publish:
        response = await reraise(_FakeRequest({"unit_id": "1", "event": "baby_cry", "score": "0.9"}))
    assert response.status_code == 303
    assert response.headers["location"] == "."
    mock_publish.assert_called_once()
    topic, payload, retain = mock_publish.call_args[0][0][0]
    assert topic == "acoustic/kitchen/event"
    assert retain is False
    assert "baby_cry" in payload


async def test_rename_writes_options_and_restarts():
    fake_info = Mock()
    fake_info.json.return_value = {"data": {"options": {"units": [{"unit_id": 1, "room": "kitchen"}]}}}
    with patch("app.main.os.environ.get", return_value="fake-token"), \
         patch("app.main.requests.get", return_value=fake_info) as mock_get, \
         patch("app.main.requests.post") as mock_post, \
         patch("app.main._mqtt_publish_once", new_callable=AsyncMock), \
         patch("app.main.load_config"), \
         patch("app.main.discovery_topics_for_room", return_value=[]), \
         patch("app.main.asyncio.create_task") as mock_create_task:
        response = await rename(_FakeRequest({"unit_id": "1", "room": "Living Room"}))

    assert response.status_code == 303
    assert response.headers["location"] == "."
    mock_get.assert_called_once()
    posted_options = mock_post.call_args.kwargs["json"]["options"]
    assert posted_options["units"][0]["room"] == "living_room"
    mock_create_task.assert_called_once()  # restart scheduled


async def test_rename_noop_on_room_collision():
    fake_info = Mock()
    fake_info.json.return_value = {"data": {"options": {"units": [
        {"unit_id": 1, "room": "kitchen"}, {"unit_id": 2, "room": "office"},
    ]}}}
    with patch("app.main.os.environ.get", return_value="fake-token"), \
         patch("app.main.requests.get", return_value=fake_info), \
         patch("app.main.requests.post") as mock_post, \
         patch("app.main.asyncio.create_task") as mock_create_task:
        response = await rename(_FakeRequest({"unit_id": "1", "room": "office"}))

    assert response.status_code == 303
    mock_post.assert_not_called()
    mock_create_task.assert_not_called()


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
