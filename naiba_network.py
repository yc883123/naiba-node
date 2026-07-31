import contextvars
import importlib.util
import os
import re
import time
import urllib.parse
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass

import requests


PROXY_MODE_HEADER = "X-Naiba-Proxy-Mode"
PROXY_URL_HEADER = "X-Naiba-Proxy-Url"
_VALID_PROXY_MODES = {"auto", "manual", "direct"}
_VALID_PROXY_SCHEMES = {"http", "https", "socks5", "socks5h"}
_SECRET_QUERY_KEYS = {
    "api_key", "apikey", "key", "token", "access_token", "auth_token",
    "password", "passwd", "user_id",
}


@dataclass(frozen=True)
class ProxySettings:
    mode: str = "auto"
    url: str = ""


@dataclass(frozen=True)
class NetworkResponse:
    content: bytes
    status: int
    elapsed_ms: int
    proxy_source: str


class NetworkRequestError(RuntimeError):
    def __init__(self, code, message, *, status=None, proxy_source="unknown"):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.proxy_source = proxy_source

    def to_dict(self):
        data = {
            "code": self.code,
            "message": self.message,
            "proxy_source": self.proxy_source,
        }
        if self.status is not None:
            data["status"] = self.status
        return data


_PROXY_CONTEXT = contextvars.ContextVar(
    "naiba_proxy_settings", default=ProxySettings()
)


def normalize_proxy_url(value):
    value = str(value or "").strip()
    if not value:
        return ""
    if "://" not in value:
        value = "http://" + value
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise NetworkRequestError(
            "proxy_config", "代理地址或端口格式无效", proxy_source="manual"
        ) from error
    if parsed.scheme.lower() not in _VALID_PROXY_SCHEMES:
        raise NetworkRequestError(
            "proxy_config",
            "代理协议仅支持 HTTP、HTTPS、SOCKS5 和 SOCKS5H",
            proxy_source="manual",
        )
    if not parsed.hostname or port is None:
        raise NetworkRequestError(
            "proxy_config", "代理地址必须包含主机和端口", proxy_source="manual"
        )
    return urllib.parse.urlunsplit(
        (parsed.scheme.lower(), parsed.netloc, parsed.path, parsed.query, "")
    )


def normalize_proxy_settings(mode="auto", url=""):
    mode = str(mode or "auto").strip().lower()
    if mode not in _VALID_PROXY_MODES:
        raise NetworkRequestError(
            "proxy_config", "代理模式无效", proxy_source="manual"
        )
    normalized_url = normalize_proxy_url(url) if mode == "manual" and url else ""
    if mode == "manual" and not normalized_url:
        raise NetworkRequestError(
            "proxy_config", "手动模式需要填写代理地址", proxy_source="manual"
        )
    return ProxySettings(mode=mode, url=normalized_url)


def proxy_settings_from_request(request):
    mode = request.headers.get(PROXY_MODE_HEADER, "auto")
    url = urllib.parse.unquote(request.headers.get(PROXY_URL_HEADER, ""))
    if len(url) > 2048:
        raise NetworkRequestError(
            "proxy_config", "代理地址过长", proxy_source="manual"
        )
    return normalize_proxy_settings(mode, url)


@contextmanager
def proxy_context(mode="auto", url=""):
    settings = normalize_proxy_settings(mode, url)
    token = _PROXY_CONTEXT.set(settings)
    try:
        yield settings
    finally:
        _PROXY_CONTEXT.reset(token)


def run_with_proxy(fn, args, mode="auto", url=""):
    with proxy_context(mode, url):
        return fn(*args)


def redact_url(value):
    value = str(value or "")
    try:
        parsed = urllib.parse.urlsplit(value)
        if not parsed.scheme or not parsed.netloc:
            return value
        hostname = parsed.hostname or ""
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        netloc = hostname
        if parsed.port is not None:
            netloc += f":{parsed.port}"
        query = []
        for key, item in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True):
            query.append((key, "***" if key.lower() in _SECRET_QUERY_KEYS else item))
        return urllib.parse.urlunsplit(
            (parsed.scheme, netloc, parsed.path, urllib.parse.urlencode(query), "")
        )
    except Exception:
        return re.sub(r"(?i)(api_key|user_id|token|password)=([^&\s]+)", r"\1=***", value)


def _proxy_source_from_environment():
    if (os.environ.get("NAIBA_PROXY_URL") or "").strip():
        return "naiba_env"
    if any((os.environ.get(name) or "").strip() for name in (
        "HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy",
        "ALL_PROXY", "all_proxy",
    )):
        return "environment"
    try:
        return "system" if urllib.request.getproxies() else "direct"
    except Exception:
        return "direct"


def _request_proxy_config(settings):
    if settings.mode == "direct":
        return False, None, "direct"

    if settings.mode == "manual":
        proxy_url = settings.url
        source = "manual"
    else:
        naiba_proxy = (os.environ.get("NAIBA_PROXY_URL") or "").strip()
        if not naiba_proxy:
            try:
                detected = urllib.request.getproxies()
            except Exception:
                detected = {}
            if importlib.util.find_spec("socks") is None and any(
                str(value or "").lower().startswith(("socks5://", "socks5h://"))
                for value in detected.values()
            ):
                raise NetworkRequestError(
                    "proxy_config",
                    "SOCKS 代理需要安装 PySocks",
                    proxy_source=_proxy_source_from_environment(),
                )
            return True, None, _proxy_source_from_environment()
        proxy_url = normalize_proxy_url(naiba_proxy)
        source = "naiba_env"

    scheme = urllib.parse.urlsplit(proxy_url).scheme.lower()
    if scheme.startswith("socks") and importlib.util.find_spec("socks") is None:
        raise NetworkRequestError(
            "proxy_config",
            "SOCKS 代理需要安装 PySocks",
            proxy_source=source,
        )
    return False, {"http": proxy_url, "https": proxy_url}, source


def _request_error(error, proxy_source):
    if isinstance(error, requests.exceptions.ProxyError):
        return NetworkRequestError(
            "proxy_error", "无法连接代理，请检查代理地址、端口和协议",
            proxy_source=proxy_source,
        )
    if isinstance(error, requests.exceptions.SSLError):
        return NetworkRequestError(
            "tls_error", "TLS 证书校验失败，请检查代理证书或系统时间",
            proxy_source=proxy_source,
        )
    if isinstance(error, requests.exceptions.Timeout):
        return NetworkRequestError(
            "timeout", "连接目标站点超时", proxy_source=proxy_source
        )
    if isinstance(error, requests.exceptions.ConnectionError):
        return NetworkRequestError(
            "connection_error", "无法解析或连接目标站点",
            proxy_source=proxy_source,
        )
    return NetworkRequestError(
        "network_error", "网络请求失败", proxy_source=proxy_source
    )


def fetch(
    url,
    *,
    headers=None,
    timeout=15,
    retries=1,
    backoff=1.0,
    retry_statuses=(429, 500, 502, 503, 504),
):
    settings = _PROXY_CONTEXT.get()
    trust_env, proxies, proxy_source = _request_proxy_config(settings)
    session = requests.Session()
    session.trust_env = trust_env
    timeout = max(0.1, float(timeout))
    request_timeout = (min(5.0, timeout), timeout)
    retries = max(0, min(int(retries), 1))
    safe_url = redact_url(url)
    started = time.monotonic()

    try:
        for attempt in range(retries + 1):
            try:
                response = session.get(
                    url,
                    headers=headers,
                    timeout=request_timeout,
                    proxies=proxies,
                )
            except requests.exceptions.Timeout as error:
                if attempt < retries:
                    time.sleep(max(0.0, float(backoff)))
                    continue
                raise _request_error(error, proxy_source) from error
            except requests.exceptions.RequestException as error:
                raise _request_error(error, proxy_source) from error

            if response.status_code in retry_statuses and attempt < retries:
                retry_after = response.headers.get("Retry-After", "")
                try:
                    delay = min(5.0, max(0.0, float(retry_after)))
                except (TypeError, ValueError):
                    delay = max(0.0, float(backoff))
                time.sleep(delay)
                continue
            if response.status_code >= 400:
                raise NetworkRequestError(
                    "http_error",
                    f"目标站点返回 HTTP {response.status_code}",
                    status=response.status_code,
                    proxy_source=proxy_source,
                )
            return NetworkResponse(
                content=response.content,
                status=response.status_code,
                elapsed_ms=round((time.monotonic() - started) * 1000),
                proxy_source=proxy_source,
            )
    except NetworkRequestError as error:
        print(
            f"[naiba_network] {error.code}: {safe_url} "
            f"({error.message}, proxy={error.proxy_source})"
        )
        raise
    finally:
        session.close()


def fetch_bytes(url, **kwargs):
    return fetch(url, **kwargs).content
