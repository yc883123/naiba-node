import asyncio
import importlib.util
import json
import os
import sys
import types
from pathlib import Path


ROOT = Path(os.environ.get("NAIBA_TEST_ROOT", Path(__file__).resolve().parents[1]))
PACKAGE_NAME = "naiba_test_civitai_tests"


def load_module(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / filename)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


package = types.ModuleType(PACKAGE_NAME)
package.__path__ = [str(ROOT)]
sys.modules[PACKAGE_NAME] = package
network = load_module(f"{PACKAGE_NAME}.naiba_network", "naiba_network.py")
civitai = load_module(f"{PACKAGE_NAME}.civitai_utils", "civitai_utils.py")


def test_client_request_preserves_proxy_context_in_worker_thread(monkeypatch):
    captured = {}

    def fake_fetch(url, **kwargs):
        captured["settings"] = network._PROXY_CONTEXT.get()
        return network.NetworkResponse(b'{"id": 1}', 200, 12, "manual")

    monkeypatch.setattr(civitai, "fetch", fake_fetch)
    client = civitai.CivitaiClient()
    with network.proxy_context("manual", "127.0.0.1:7890"):
        data, error = asyncio.run(client.query_by_hash("a" * 64))

    assert error is None
    assert data == {"id": 1}
    assert captured["settings"].mode == "manual"
    assert captured["settings"].url == "http://127.0.0.1:7890"


def test_hash_404_is_distinct_from_network_failure(monkeypatch):
    def not_found(*_args, **_kwargs):
        raise network.NetworkRequestError(
            "http_error", "目标站点返回 HTTP 404", status=404, proxy_source="direct"
        )

    monkeypatch.setattr(civitai, "fetch", not_found)
    data, error = asyncio.run(civitai.CivitaiClient().query_by_hash("b" * 64))

    assert data is None
    assert error.code == "not_found"
    assert civitai.classify_civitai_lookup(True, None, error) == "local_only"
    assert civitai.classify_civitai_lookup(False, None, error) == "not_found"


def test_network_failure_is_never_classified_as_verified(monkeypatch):
    error = civitai.CivitaiError(
        "无法连接代理", "proxy_error", proxy_source="manual"
    )
    assert civitai.classify_civitai_lookup(True, None, error) == "query_failed"
    assert civitai.classify_civitai_lookup(False, None, error) == "query_failed"


def test_has_synced_metadata_requires_civitai_identity():
    assert not civitai.has_synced_metadata(None)
    assert not civitai.has_synced_metadata({})
    assert not civitai.has_synced_metadata({"hash": "a" * 64})
    assert not civitai.has_synced_metadata({
        "hash": "a" * 64,
        "version_id": 123,
        "_sha_only": True,
    })

    assert civitai.has_synced_metadata({"version_id": 123})
    assert civitai.has_synced_metadata({"model_id": 456})
    assert civitai.has_synced_metadata({"model_name": "Example"})
    assert civitai.has_synced_metadata({"version_name": "v1"})


def test_preview_failure_is_saved_as_retryable(monkeypatch, tmp_path):
    lora_path = tmp_path / "sample.safetensors"
    lora_path.write_bytes(b"lora")
    calls = {"query": 0, "download": 0}
    version = {
        "id": 10,
        "modelId": 20,
        "name": "v1",
        "images": [{"url": "https://image.civitai.com/sample.png", "nsfwLevel": 1}],
    }

    async def fake_query(self, _file_hash, max_retries=1):
        calls["query"] += 1
        return version, None

    async def fake_download(self, _url, _path, validate=True):
        calls["download"] += 1
        self.last_error = civitai.CivitaiError("CDN timeout", "timeout")
        return False

    monkeypatch.setattr(civitai.CivitaiClient, "calculate_sha256", lambda _path: "c" * 64)
    monkeypatch.setattr(civitai.CivitaiClient, "query_by_hash", fake_query)
    monkeypatch.setattr(civitai.CivitaiClient, "download_image", fake_download)

    metadata, preview, error = asyncio.run(civitai.sync_lora_from_civitai(str(lora_path)))
    assert preview is None
    assert error.code == "timeout"
    assert metadata["_preview_status"] == "failed"
    assert metadata["_preview_resolved"] is False

    cache = json.loads((tmp_path / "sample.civitai.info.json").read_text("utf-8"))
    assert cache["_preview_status"] == "failed"

    asyncio.run(civitai.sync_lora_from_civitai(str(lora_path)))
    assert calls == {"query": 2, "download": 2}


def test_genuine_no_preview_is_cached_without_requery(monkeypatch, tmp_path):
    lora_path = tmp_path / "no-preview.safetensors"
    lora_path.write_bytes(b"lora")
    calls = {"query": 0}

    async def fake_query(self, _file_hash, max_retries=1):
        calls["query"] += 1
        return {"id": 1, "modelId": 2, "images": []}, None

    monkeypatch.setattr(civitai.CivitaiClient, "calculate_sha256", lambda _path: "d" * 64)
    monkeypatch.setattr(civitai.CivitaiClient, "query_by_hash", fake_query)

    first = asyncio.run(civitai.sync_lora_from_civitai(str(lora_path)))
    second = asyncio.run(civitai.sync_lora_from_civitai(str(lora_path)))

    assert first[0]["_preview_status"] == "none"
    assert first[2] is None and second[2] is None
    assert calls["query"] == 1


def test_metadata_write_failure_is_reported(monkeypatch, tmp_path):
    lora_path = tmp_path / "readonly.safetensors"
    lora_path.write_bytes(b"lora")

    async def fake_query(self, _file_hash, max_retries=1):
        return {"id": 1, "modelId": 2, "images": []}, None

    monkeypatch.setattr(civitai.CivitaiClient, "calculate_sha256", lambda _path: "e" * 64)
    monkeypatch.setattr(civitai.CivitaiClient, "query_by_hash", fake_query)
    monkeypatch.setattr(civitai, "save_cached_metadata", lambda *_args: False)

    _metadata, _preview, error = asyncio.run(
        civitai.sync_lora_from_civitai(str(lora_path), force=True)
    )
    assert error.code == "storage_error"


def test_force_refresh_network_failure_preserves_existing_metadata(monkeypatch, tmp_path):
    lora_path = tmp_path / "existing.safetensors"
    lora_path.write_bytes(b"lora")
    preview_path = tmp_path / "existing.preview.png"
    preview_path.write_bytes(b"image")
    metadata_path = tmp_path / "existing.civitai.info.json"
    metadata_path.write_text(json.dumps({
        "hash": "f" * 64,
        "model_name": "Keep me",
        "preview_path": str(preview_path),
        "_preview_status": "downloaded",
    }), "utf-8")

    async def failed_query(self, _file_hash, max_retries=1):
        return None, civitai.CivitaiError("proxy down", "proxy_error")

    monkeypatch.setattr(civitai.CivitaiClient, "calculate_sha256", lambda _path: "f" * 64)
    monkeypatch.setattr(civitai.CivitaiClient, "query_by_hash", failed_query)

    metadata, preview, error = asyncio.run(
        civitai.sync_lora_from_civitai(str(lora_path), force=True)
    )
    persisted = json.loads(metadata_path.read_text("utf-8"))

    assert error.code == "proxy_error"
    assert metadata["model_name"] == "Keep me"
    assert preview == str(preview_path)
    assert persisted["model_name"] == "Keep me"
    assert persisted["_last_sync_error"] == "proxy down"


def test_supported_modern_image_magic_is_accepted():
    assert civitai._looks_like_image(b"\x00\x00\x00\x18avif" + b"\x00" * 12)
    assert civitai._looks_like_image(b"BM" + b"\x00" * 10)
    assert civitai._looks_like_image(b"\x00\x00\x01\x00" + b"\x00" * 8)
