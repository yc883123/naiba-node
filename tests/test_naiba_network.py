import importlib.util
import os
import sys
import types
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "naiba_test_network_tests"


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


folder_paths = types.ModuleType("folder_paths")
sys.modules.setdefault("folder_paths", folder_paths)


def load_picker(filename):
    name = filename.removesuffix(".py")
    module_name = f"{PACKAGE_NAME}.{name}"
    return sys.modules.get(module_name) or load_module(module_name, filename)


class FakeResponse:
    def __init__(self, status=200, content=b"ok", headers=None):
        self.status_code = status
        self.content = content
        self.headers = headers or {}


class FakeSession:
    def __init__(self, scripted, calls):
        self.scripted = scripted
        self.calls = calls
        self.trust_env = True

    def get(self, url, **kwargs):
        self.calls.append({"url": url, "trust_env": self.trust_env, **kwargs})
        item = self.scripted.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        pass


def install_fake_session(monkeypatch, scripted):
    calls = []
    scripted = list(scripted)
    monkeypatch.setattr(
        network.requests,
        "Session",
        lambda: FakeSession(scripted, calls),
    )
    return calls


def clear_proxy_env(monkeypatch):
    for name in (
        "NAIBA_PROXY_URL", "HTTPS_PROXY", "https_proxy", "HTTP_PROXY",
        "http_proxy", "ALL_PROXY", "all_proxy", "NO_PROXY", "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)


def test_proxy_url_normalization_and_validation():
    assert network.normalize_proxy_url("127.0.0.1:7890") == "http://127.0.0.1:7890"
    assert network.normalize_proxy_url("socks5h://localhost:1080") == "socks5h://localhost:1080"
    with pytest.raises(network.NetworkRequestError) as error:
        network.normalize_proxy_url("ftp://127.0.0.1:21")
    assert error.value.code == "proxy_config"


def test_request_headers_decode_manual_proxy_and_ignore_stale_auto_url():
    class Request:
        def __init__(self, mode, url):
            self.headers = {
                network.PROXY_MODE_HEADER: mode,
                network.PROXY_URL_HEADER: url,
            }

    manual = network.proxy_settings_from_request(
        Request("manual", "http%3A%2F%2F127.0.0.1%3A7890")
    )
    assert manual.url == "http://127.0.0.1:7890"
    auto = network.proxy_settings_from_request(Request("auto", "%broken"))
    assert auto.url == ""


def test_manual_proxy_overrides_environment(monkeypatch):
    clear_proxy_env(monkeypatch)
    monkeypatch.setenv("HTTPS_PROXY", "http://environment:9000")
    calls = install_fake_session(monkeypatch, [FakeResponse()])
    with network.proxy_context("manual", "127.0.0.1:7890"):
        result = network.fetch("https://example.test/data", retries=0)
    assert result.proxy_source == "manual"
    assert calls[0]["trust_env"] is False
    assert calls[0]["proxies"] == {
        "http": "http://127.0.0.1:7890",
        "https": "http://127.0.0.1:7890",
    }


def test_auto_naiba_proxy_and_direct_mode(monkeypatch):
    clear_proxy_env(monkeypatch)
    monkeypatch.setenv("NAIBA_PROXY_URL", "127.0.0.1:7891")
    calls = install_fake_session(monkeypatch, [FakeResponse(), FakeResponse()])
    with network.proxy_context("auto", ""):
        auto_result = network.fetch("https://example.test/auto", retries=0)
    with network.proxy_context("direct", ""):
        direct_result = network.fetch("https://example.test/direct", retries=0)
    assert auto_result.proxy_source == "naiba_env"
    assert calls[0]["proxies"]["https"] == "http://127.0.0.1:7891"
    assert calls[0]["trust_env"] is False
    assert direct_result.proxy_source == "direct"
    assert calls[1]["proxies"] is None
    assert calls[1]["trust_env"] is False


def test_auto_standard_proxy_is_resolved_for_each_request(monkeypatch):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(monkeypatch, [FakeResponse(), FakeResponse()])
    monkeypatch.setenv("HTTPS_PROXY", "http://first:8000")
    network.fetch("https://example.test/one", retries=0)
    monkeypatch.setenv("HTTPS_PROXY", "http://second:8000")
    network.fetch("https://example.test/two", retries=0)
    assert len(calls) == 2
    assert all(call["trust_env"] is True for call in calls)
    assert all(call["proxies"] is None for call in calls)


def test_socks_missing_dependency_fails_without_request(monkeypatch):
    clear_proxy_env(monkeypatch)
    monkeypatch.setattr(network.importlib.util, "find_spec", lambda _name: None)
    calls = install_fake_session(monkeypatch, [FakeResponse()])
    with network.proxy_context("manual", "socks5://127.0.0.1:1080"):
        with pytest.raises(network.NetworkRequestError) as error:
            network.fetch("https://example.test", retries=0)
    assert error.value.code == "proxy_config"
    assert calls == []


def test_auto_socks_missing_dependency_is_reported(monkeypatch):
    clear_proxy_env(monkeypatch)
    monkeypatch.setattr(network.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(
        network.urllib.request,
        "getproxies",
        lambda: {"https": "socks5://127.0.0.1:1080"},
    )
    calls = install_fake_session(monkeypatch, [FakeResponse()])
    with pytest.raises(network.NetworkRequestError) as error:
        network.fetch("https://example.test", retries=0)
    assert error.value.code == "proxy_config"
    assert calls == []


def test_retry_is_limited_to_one_transient_response(monkeypatch):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(
        monkeypatch, [FakeResponse(503), FakeResponse(200, b"done")]
    )
    monkeypatch.setattr(network.time, "sleep", lambda _delay: None)
    result = network.fetch("https://example.test", retries=5)
    assert result.content == b"done"
    assert len(calls) == 2


def test_proxy_error_is_not_retried(monkeypatch):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(
        monkeypatch, [requests.exceptions.ProxyError("proxy unavailable")]
    )
    with pytest.raises(network.NetworkRequestError) as error:
        network.fetch("https://example.test", retries=1)
    assert error.value.code == "proxy_error"
    assert len(calls) == 1


@pytest.mark.parametrize(
    ("raised", "code"),
    [
        (requests.exceptions.SSLError("bad certificate"), "tls_error"),
        (requests.exceptions.ConnectionError("dns failed"), "connection_error"),
    ],
)
def test_deterministic_connection_errors_are_not_retried(monkeypatch, raised, code):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(monkeypatch, [raised])
    with pytest.raises(network.NetworkRequestError) as error:
        network.fetch("https://example.test", retries=1)
    assert error.value.code == code
    assert len(calls) == 1


def test_timeout_retries_only_once(monkeypatch):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(
        monkeypatch,
        [requests.exceptions.Timeout("slow"), FakeResponse(200, b"done")],
    )
    monkeypatch.setattr(network.time, "sleep", lambda _delay: None)
    result = network.fetch("https://example.test", retries=9)
    assert result.content == b"done"
    assert len(calls) == 2


def test_url_and_error_output_are_redacted(monkeypatch, capsys):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(monkeypatch, [FakeResponse(401)])
    secret_url = (
        "https://user:password@example.test/path?api_key=secret&user_id=42&q=ok"
    )
    with pytest.raises(network.NetworkRequestError):
        network.fetch(secret_url, retries=0)
    output = capsys.readouterr().out
    assert "secret" not in output
    assert "password" not in output
    assert "user:password" not in output
    assert "api_key=%2A%2A%2A" in output
    assert calls[0]["url"] == secret_url


def test_context_is_restored_after_manual_request(monkeypatch):
    clear_proxy_env(monkeypatch)
    calls = install_fake_session(monkeypatch, [FakeResponse(), FakeResponse()])
    network.run_with_proxy(
        lambda: network.fetch("https://example.test/manual", retries=0),
        (),
        "manual",
        "127.0.0.1:7890",
    )
    network.fetch("https://example.test/auto", retries=0)
    assert calls[0]["proxies"]["https"] == "http://127.0.0.1:7890"
    assert calls[1]["proxies"] is None


class FakeDiskCache:
    def __init__(self, value=None):
        self.value = value

    def get_json(self, _key):
        return dict(self.value) if self.value is not None else None

    def set_json(self, _key, _value):
        pass


def test_danbooru_search_uses_cache_with_network_warning(monkeypatch):
    picker = load_picker("naiba_tag_picker.py")
    picker._DISK_CACHE = FakeDiskCache({"items": [{"tag": "cached"}], "total": 1})

    def fail(_url, **_kwargs):
        raise network.NetworkRequestError("timeout", "连接目标站点超时")

    monkeypatch.setattr(picker, "_fetch_url", fail)
    result = picker.search_tags("cached", "tag", 10, 1)
    assert result["cached"] is True
    assert result["warning"]["code"] == "timeout"
    assert result["items"][0]["tag"] == "cached"


def test_danbooru_search_distinguishes_empty_from_network_failure(monkeypatch):
    picker = load_picker("naiba_tag_picker.py")
    picker._DISK_CACHE = None
    monkeypatch.setattr(picker, "_fetch_url", lambda _url, **_kwargs: b"[]")
    assert picker.search_tags("none", "tag", 10, 1)["items"] == []

    def fail(_url, **_kwargs):
        raise network.NetworkRequestError("connection_error", "无法连接")

    monkeypatch.setattr(picker, "_fetch_url", fail)
    with pytest.raises(network.NetworkRequestError):
        picker.search_tags("none", "tag", 10, 1)


def test_gelbooru_search_uses_cache_with_network_warning(monkeypatch):
    picker = load_picker("naiba_gelbooru_tag_picker.py")
    picker._DISK_CACHE = FakeDiskCache({"items": [{"tag": "cached"}], "total": 1})

    def fail(*_args, **_kwargs):
        raise network.NetworkRequestError("proxy_error", "无法连接代理")

    monkeypatch.setattr(picker, "_autocomplete_search", fail)
    result = picker.search_tags("cached", "tag", 10, 1)
    assert result["cached"] is True
    assert result["warning"]["code"] == "proxy_error"


def test_gelbooru_search_distinguishes_empty_from_network_failure(monkeypatch):
    picker = load_picker("naiba_gelbooru_tag_picker.py")
    picker._DISK_CACHE = None
    monkeypatch.setattr(picker, "_autocomplete_search", lambda *_args: [])
    assert picker.search_tags("none", "tag", 10, 1)["items"] == []

    def fail(*_args, **_kwargs):
        raise network.NetworkRequestError("tls_error", "TLS 证书校验失败")

    monkeypatch.setattr(picker, "_autocomplete_search", fail)
    with pytest.raises(network.NetworkRequestError):
        picker.search_tags("none", "tag", 10, 1)
