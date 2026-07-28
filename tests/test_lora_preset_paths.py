import importlib.util
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "lora_preset_paths.py"
SPEC = importlib.util.spec_from_file_location("lora_preset_paths", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
SHA_D = "d" * 64


def test_classifies_unique_ambiguous_stale_and_missing_paths_by_index():
    items = [
        {"name": "same\\model.safetensors", "sha256": SHA_A},
        {"name": "foreign/model.safetensors", "sha256": SHA_B, "enabled": False},
        {"name": "foreign/duplicate.safetensors", "sha256": SHA_C},
        {"name": "foreign/stale.safetensors", "sha256": SHA_D},
        {"name": "foreign/missing.safetensors", "sha256": "e" * 64},
        {"name": "foreign/no-hash.safetensors"},
    ]
    candidates = {
        SHA_A: ["same/model.safetensors", "other/copy.safetensors"],
        SHA_B: ["local/model.safetensors"],
        SHA_C: ["local/a.safetensors", "local/b.safetensors"],
        SHA_D: ["local/stale.safetensors"],
    }
    states = {
        "same/model.safetensors": "current",
        "other/copy.safetensors": "current",
        "local/model.safetensors": "current",
        "local/a.safetensors": "current",
        "local/b.safetensors": "current",
        "local/stale.safetensors": "stale",
    }

    result = MODULE.classify_preset_paths(
        items, candidates, lambda name: states[name]
    )

    assert result["relocations"] == [{
        "preset_index": 1,
        "original_name": "foreign/model.safetensors",
        "local_name": "local/model.safetensors",
        "sha256": SHA_B,
        "enabled": False,
    }]
    assert result["ambiguous"][0]["preset_index"] == 2
    assert result["ambiguous"][0]["candidates"] == [
        "local/a.safetensors", "local/b.safetensors"
    ]
    assert result["stale_cache"][0]["preset_index"] == 3
    assert result["local_candidates"][0] == ["same/model.safetensors"]
    assert result["path_summary"] == {
        "total": 6,
        "same": 1,
        "relocations": 1,
        "ambiguous": 1,
        "missing": 1,
        "stale_cache": 1,
        "no_sha256": 1,
    }


def test_invalid_or_short_hash_is_not_used_for_matching():
    result = MODULE.classify_preset_paths(
        [
            {"name": "one.safetensors", "sha256": "abc123"},
            {"name": "two.safetensors", "sha256": "z" * 64},
        ],
        {"abc123": ["local/one.safetensors"]},
        lambda _name: "current",
    )

    assert result["relocations"] == []
    assert result["path_summary"]["no_sha256"] == 2


def test_duplicate_cached_paths_are_deduplicated_without_file_reads():
    inspected = []
    result = MODULE.classify_preset_paths(
        [{"name": "foreign.safetensors", "sha256": SHA_A}],
        {SHA_A: ["local\\model.safetensors", "local/model.safetensors"]},
        lambda name: inspected.append(name) or "current",
    )

    assert inspected == ["local/model.safetensors"]
    assert result["relocations"][0]["local_name"] == "local/model.safetensors"


def test_resolve_never_replaces_current_paths_with_stale_cache_candidates():
    items = [
        {"name": "old/first.safetensors", "sha256": SHA_A, "enabled": True},
        {"name": "local/second.safetensors", "sha256": SHA_B, "enabled": True},
        {"name": "local/third.safetensors", "sha256": SHA_C, "custom": 123},
    ]
    candidates = {
        SHA_A: ["local/first.safetensors", "old/first.safetensors"],
        SHA_B: ["local/second.safetensors", "old/second.safetensors"],
        SHA_C: ["old/third.safetensors", "local/third.safetensors"],
    }
    states = {
        "local/first.safetensors": "current",
        "old/first.safetensors": "missing",
        "local/second.safetensors": "current",
        "old/second.safetensors": "missing",
        "local/third.safetensors": "current",
        "old/third.safetensors": "missing",
    }

    resolved = MODULE.resolve_preset_paths(
        items,
        candidates,
        lambda name: states[name],
        lambda name: states.get(name) == "current",
    )

    assert [item["name"] for item in resolved] == [
        "local/first.safetensors",
        "local/second.safetensors",
        "local/third.safetensors",
    ]
    assert resolved[2]["custom"] == 123
    assert items[0]["name"] == "old/first.safetensors"


def test_resolve_does_not_guess_when_multiple_current_candidates_exist():
    original = {"name": "foreign/model.safetensors", "sha256": SHA_A}
    resolved = MODULE.resolve_preset_paths(
        [original],
        {SHA_A: ["local/a.safetensors", "local/b.safetensors"]},
        lambda _name: "current",
        lambda _name: False,
    )

    assert resolved[0]["name"] == "foreign/model.safetensors"


if __name__ == "__main__":
    test_classifies_unique_ambiguous_stale_and_missing_paths_by_index()
    test_invalid_or_short_hash_is_not_used_for_matching()
    test_duplicate_cached_paths_are_deduplicated_without_file_reads()
    test_resolve_never_replaces_current_paths_with_stale_cache_candidates()
    test_resolve_does_not_guess_when_multiple_current_candidates_exist()
    print("lora preset path tests passed")
