import builtins
import importlib.util
import os
import tempfile
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "sha256_cache.py"
SPEC = importlib.util.spec_from_file_location("naiba_sha256_cache_test", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def reset_cache(tmp_path):
    MODULE._CACHE_PATH = str(tmp_path / "cache.json")
    MODULE._MEM = {"version": 1, "entries": {}}
    MODULE._SHA_CANDIDATES_INDEX = None


def test_reverse_index_keeps_all_candidates_and_invalidates_on_update():
    with tempfile.TemporaryDirectory(dir=MODULE_PATH.parent) as temp_dir:
        tmp_path = Path(temp_dir)
        reset_cache(tmp_path)
        first = tmp_path / "first.safetensors"
        second = tmp_path / "second.safetensors"
        third = tmp_path / "third.safetensors"
        first.write_bytes(b"first")
        second.write_bytes(b"second")
        third.write_bytes(b"third")
        shared_sha = "a" * 64

        MODULE.update_entry("z/second.safetensors", shared_sha, str(second))
        MODULE.update_entry("a/first.safetensors", shared_sha, str(first))
        assert MODULE.build_sha_candidates_index()[shared_sha] == [
            "a/first.safetensors", "z/second.safetensors"
        ]

        MODULE.update_entry("third.safetensors", "b" * 64, str(third))
        assert MODULE.build_sha_candidates_index()["b" * 64] == ["third.safetensors"]


def test_entry_state_uses_stat_without_opening_lora_file():
    with tempfile.TemporaryDirectory(dir=MODULE_PATH.parent) as temp_dir:
        tmp_path = Path(temp_dir)
        reset_cache(tmp_path)
        lora_path = tmp_path / "model.safetensors"
        lora_path.write_bytes(b"model data")
        MODULE.update_entry("model.safetensors", "c" * 64, str(lora_path))

        real_open = builtins.open

        def guarded_open(file, *args, **kwargs):
            if str(file).lower().endswith(".safetensors"):
                raise AssertionError("verification must not open LoRA files")
            return real_open(file, *args, **kwargs)

        with patch("builtins.open", guarded_open):
            assert MODULE.check_entry_state("model.safetensors", str(lora_path)) == "current"
            assert MODULE.build_sha_candidates_index()["c" * 64] == ["model.safetensors"]

            stat = lora_path.stat()
            os.utime(lora_path, (stat.st_atime, stat.st_mtime + 5))
            assert MODULE.check_entry_state("model.safetensors", str(lora_path)) == "stale"


def test_status_counts_only_current_local_entries_and_separates_orphans():
    with tempfile.TemporaryDirectory(dir=MODULE_PATH.parent) as temp_dir:
        tmp_path = Path(temp_dir)
        reset_cache(tmp_path)
        current_path = tmp_path / "current.safetensors"
        stale_path = tmp_path / "stale.safetensors"
        current_path.write_bytes(b"current")
        stale_path.write_bytes(b"stale")

        MODULE.update_entry("current.safetensors", "d" * 64, str(current_path))
        MODULE.update_entry("stale.safetensors", "e" * 64, str(stale_path))
        MODULE.update_entry("deleted.safetensors", "f" * 64)
        stale_path.write_bytes(b"stale changed")

        status = MODULE.summarize_local_entries([
            ("current.safetensors", str(current_path)),
            ("stale.safetensors", str(stale_path)),
            ("uncached.safetensors", str(tmp_path / "uncached.safetensors")),
        ])

        assert status["cached_count"] == 1
        assert status["cache_entry_count"] == 3
        assert status["total_loras"] == 3
        assert status["missing_count"] == 2
        assert status["stale_count"] == 1
        assert status["orphaned_count"] == 1
        assert status["all_cached"] is False
        assert status["stale"] == ["stale.safetensors"]
        assert status["orphaned"] == ["deleted.safetensors"]


if __name__ == "__main__":
    test_reverse_index_keeps_all_candidates_and_invalidates_on_update()
    test_entry_state_uses_stat_without_opening_lora_file()
    test_status_counts_only_current_local_entries_and_separates_orphans()
    print("sha256 cache tests passed")
