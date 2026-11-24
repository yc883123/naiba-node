import importlib.util
import json
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "preset_categories.py"
SPEC = importlib.util.spec_from_file_location("preset_categories", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def write_store(presets_dir, payload):
    meta_dir = Path(presets_dir) / MODULE.META_DIRNAME
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / MODULE.STORE_FILENAME).write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def test_create_category_persists_to_meta_file(tmp_path):
    store = MODULE.create_category(str(tmp_path), "  动漫   风格 ")
    store = MODULE.create_category(str(tmp_path), "写实")

    assert store["categories"] == ["动漫 风格", "写实"]
    saved = json.loads(
        (tmp_path / MODULE.META_DIRNAME / MODULE.STORE_FILENAME).read_text(
            encoding="utf-8"
        )
    )
    assert saved["categories"] == ["动漫 风格", "写实"]
    # 元数据不放在 presets 根目录，避免被预设列表接口当成预设
    assert not list(tmp_path.glob("*.json"))


def test_category_name_validation(tmp_path):
    MODULE.create_category(str(tmp_path), "Anime")

    with pytest.raises(ValueError, match="已存在"):
        MODULE.create_category(str(tmp_path), "anime")
    with pytest.raises(ValueError, match="未分类"):
        MODULE.create_category(str(tmp_path), "未分类")
    with pytest.raises(ValueError, match="32"):
        MODULE.create_category(str(tmp_path), "x" * 33)
    with pytest.raises(ValueError, match="不能为空"):
        MODULE.create_category(str(tmp_path), "   ")


def test_rename_category_updates_assignments(tmp_path):
    presets_dir = str(tmp_path)
    MODULE.create_category(presets_dir, "动漫")
    MODULE.create_category(presets_dir, "写实")
    MODULE.set_preset_categories(presets_dir, "preset-a", ["动漫", "写实"])

    store = MODULE.rename_category(presets_dir, "动漫", "二次元")

    assert store["categories"] == ["二次元", "写实"]
    assert store["assignments"]["preset-a"] == ["二次元", "写实"]

    with pytest.raises(ValueError, match="已存在"):
        MODULE.rename_category(presets_dir, "写实", "二次元")


def test_delete_category_keeps_other_categories(tmp_path):
    presets_dir = str(tmp_path)
    MODULE.create_category(presets_dir, "动漫")
    MODULE.create_category(presets_dir, "写实")
    MODULE.set_preset_categories(presets_dir, "multi", ["动漫", "写实"])
    MODULE.set_preset_categories(presets_dir, "only-anime", ["动漫"])

    store = MODULE.delete_category(presets_dir, "动漫")

    assert store["categories"] == ["写实"]
    # 仍属于其它分类的预设保留分类；只有分类清空的预设才归入未分类（不落存储）
    assert store["assignments"] == {"multi": ["写实"]}
    assert "only-anime" not in store["assignments"]


def test_set_preset_categories_filters_unknown_and_reserved(tmp_path):
    presets_dir = str(tmp_path)
    MODULE.create_category(presets_dir, "动漫")

    assigned = MODULE.set_preset_categories(
        presets_dir, "preset-a", ["动漫", "动漫", "未分类", "不存在"]
    )
    assert assigned == ["动漫"]

    assigned = MODULE.set_preset_categories(presets_dir, "preset-a", [])
    assert assigned == []
    assert "preset-a" not in MODULE.load_store(presets_dir)["assignments"]


def test_rename_and_remove_preset_sync_assignments(tmp_path):
    presets_dir = str(tmp_path)
    MODULE.create_category(presets_dir, "动漫")
    MODULE.set_preset_categories(presets_dir, "old-name", ["动漫"])

    assert MODULE.rename_preset(presets_dir, "old-name", "new-name") is True
    store = MODULE.load_store(presets_dir)
    assert store["assignments"] == {"new-name": ["动漫"]}

    assert MODULE.remove_preset(presets_dir, "new-name") is True
    assert MODULE.load_store(presets_dir)["assignments"] == {}
    assert MODULE.remove_preset(presets_dir, "new-name") is False


def test_rename_preset_merges_existing_stale_assignment(tmp_path):
    presets_dir = str(tmp_path)
    MODULE.create_category(presets_dir, "动漫")
    MODULE.create_category(presets_dir, "写实")
    MODULE.set_preset_categories(presets_dir, "old", ["动漫"])

    store = MODULE.load_store(presets_dir)
    store["assignments"]["new"] = ["写实"]
    MODULE.save_store(presets_dir, store)

    MODULE.rename_preset(presets_dir, "old", "new")

    assert MODULE.load_store(presets_dir)["assignments"]["new"] == ["写实", "动漫"]


def test_sanitize_drops_stale_and_invalid_entries(tmp_path):
    presets_dir = str(tmp_path)
    write_store(presets_dir, {
        "version": 1,
        "categories": ["动漫", "动漫", "  ", "未分类", "Anime", "anime"],
        "assignments": {
            "good": ["动漫", "不存在", "动漫"],
            "stale": ["不存在"],
            "": ["动漫"],
            "not-list": "动漫",
        },
    })

    store = MODULE.load_store(presets_dir)

    assert store["categories"] == ["动漫", "Anime"]
    assert store["assignments"] == {"good": ["动漫"]}


def test_corrupt_store_is_backed_up_and_reset(tmp_path):
    presets_dir = str(tmp_path)
    meta_dir = tmp_path / MODULE.META_DIRNAME
    meta_dir.mkdir()
    (meta_dir / MODULE.STORE_FILENAME).write_text("{invalid json", encoding="utf-8")

    store = MODULE.load_store(presets_dir)

    assert store == {"version": 1, "categories": [], "assignments": {}}
    backups = list(meta_dir.glob(f"{MODULE.STORE_FILENAME}.corrupt-*"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "{invalid json"