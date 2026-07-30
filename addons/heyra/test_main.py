"""Run with: pytest addons/heyra-flasher/ (needs starlette installed)."""
import os

os.environ.setdefault("HEYRA_FIRMWARE_DIR", str(__import__("pathlib").Path(__file__).parent / "firmware"))

from app.main import list_boards, UNIT_TEMPLATE  # noqa: E402


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
