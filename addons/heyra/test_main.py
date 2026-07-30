"""Run with: pytest addons/heyra/ (needs starlette installed)."""
import os
from unittest.mock import Mock, patch

os.environ.setdefault("HEYRA_FIRMWARE_DIR", str(__import__("pathlib").Path(__file__).parent / "firmware"))

from app.main import (  # noqa: E402
    UNIT_TEMPLATE,
    fetch_unit_snapshot,
    list_boards,
    next_unit_id,
    render_units_html,
)


def test_list_boards_finds_atom_echo():
    assert "atom-echo" in list_boards()


def test_unit_template_renders_without_error():
    rendered = UNIT_TEMPLATE.format(
        room="kitchen", device_name="atom-echo-02", friendly_name="Heyra Kitchen",
        unit_id="2", static_ip="192.168.1.102",
        board_path="/app/firmware/boards/atom-echo.yaml", common_path="/app/firmware/common.yaml",
    )
    assert "device_name: atom-echo-02" in rendered
    assert "board: !include /app/firmware/boards/atom-echo.yaml" in rendered


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
    assert "dot-online" in rendered
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
