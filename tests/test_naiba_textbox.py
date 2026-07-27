import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "naiba_textbox.py"
SPEC = importlib.util.spec_from_file_location("naiba_textbox", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_override_switch_defaults_to_enabled():
    switch = MODULE.NaibaTextbox.INPUT_TYPES()["required"][
        "allow_passthrough_override"
    ]

    assert switch[0] == "BOOLEAN"
    assert switch[1]["default"] is True


def test_connected_empty_passthrough_clears_text_when_enabled():
    result = MODULE.NaibaTextbox().textbox(
        text="current", allow_passthrough_override=True, passthrough=""
    )

    assert result == {"ui": {"text": ""}, "result": ("",)}


def test_passthrough_overrides_text_when_enabled():
    result = MODULE.NaibaTextbox().textbox(
        text="current", allow_passthrough_override=True, passthrough="upstream"
    )

    assert result == {"ui": {"text": "upstream"}, "result": ("upstream",)}


def test_passthrough_is_ignored_when_override_is_disabled():
    node = MODULE.NaibaTextbox()

    assert node.textbox("current", False, "upstream") == ("current",)
    assert node.textbox("current", False, "") == ("current",)


def test_disconnected_passthrough_keeps_current_text():
    assert MODULE.NaibaTextbox().textbox("current", True) == ("current",)
