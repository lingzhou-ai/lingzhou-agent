"""HTTP proxy resolution shared by provider and tool HTTP clients."""
from __future__ import annotations

import os
from urllib.parse import urlparse

PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def _clean(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _env_proxy(name: str, env: dict[str, str] | None = None) -> str | None:
    env = env or os.environ
    return _clean(env.get(name))


def _target_scheme(url: str | None) -> str:
    if not url:
        return "https"
    try:
        parsed = urlparse(url)
        return "http" if parsed.scheme.lower() == "http" else "https"
    except Exception:
        return "https"


def _target_host_port(url: str) -> tuple[str, str]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower().strip("[]")
    port = str(parsed.port or (443 if parsed.scheme == "https" else 80 if parsed.scheme == "http" else ""))
    return host, port


def _matches_no_proxy_entry(host: str, port: str, entry: str) -> bool:
    if entry == "*":
        return True
    entry_host, sep, entry_port = entry.rpartition(":")
    if sep and entry_port.isdigit():
        if entry_port != port:
            return False
        entry = entry_host
    entry = entry.lower().strip().strip("[]")
    if not entry:
        return False
    if entry.startswith("*."):
        suffix = entry[2:]
        return host == suffix or host.endswith(f".{suffix}")
    if entry.startswith("."):
        suffix = entry[1:]
        return host == suffix or host.endswith(f".{suffix}")
    return host == entry or host.endswith(f".{entry}")


def matches_no_proxy(url: str, env: dict[str, str] | None = None) -> bool:
    env = env or os.environ
    raw = _env_proxy("no_proxy", env) or _env_proxy("NO_PROXY", env)
    if not raw:
        return False
    try:
        host, port = _target_host_port(url)
    except Exception:
        return False
    if not host:
        return False
    for item in raw.replace(",", " ").split():
        if _matches_no_proxy_entry(host, port, item.strip()):
            return True
    return False


def resolve_env_proxy_url(url: str | None = None, env: dict[str, str] | None = None) -> str | None:
    """Resolve env proxy with lower-case precedence and HTTPS->HTTP fallback."""
    env = env or os.environ
    if url and matches_no_proxy(url, env):
        return None
    scheme = _target_scheme(url)
    http_proxy = _env_proxy("http_proxy", env) or _env_proxy("HTTP_PROXY", env)
    https_proxy = _env_proxy("https_proxy", env) or _env_proxy("HTTPS_PROXY", env)
    all_proxy = _env_proxy("all_proxy", env) or _env_proxy("ALL_PROXY", env)
    if scheme == "http":
        return http_proxy or all_proxy
    return https_proxy or http_proxy or all_proxy


def resolve_http_proxy_url(
    url: str | None = None,
    *,
    explicit_proxy_url: str | None = None,
    trust_env: bool = True,
    env: dict[str, str] | None = None,
) -> str | None:
    explicit = _clean(explicit_proxy_url)
    if explicit:
        return explicit
    if not trust_env:
        return None
    return resolve_env_proxy_url(url, env)


def httpx_proxy_kwargs(
    url: str | None = None,
    *,
    explicit_proxy_url: str | None = None,
    trust_env: bool = True,
    env: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build httpx kwargs while making configured proxy precedence explicit."""
    proxy = resolve_http_proxy_url(
        url,
        explicit_proxy_url=explicit_proxy_url,
        trust_env=trust_env,
        env=env,
    )
    if proxy:
        return {"proxy": proxy, "trust_env": False}
    return {"trust_env": trust_env}
