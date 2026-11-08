"""Provider clients of the infrastructure panel (INFRA_PANEL_DESIGN 2). One module per provider, each with:

- `NAME` (the `infra_snapshots.provider` key), `connection()` -> "connected" | "not_connected" | "unavailable",
- `dashboard_url()` (a constant link, never a token),
- `fetch(client: httpx.Client)` -> a typed dataclass of the allow-listed fields (never a raw response).

Tokens travel only in request headers, never in URLs. A failure is a `ProviderError(code, http_status)`: the code is a
fixed word and nothing of the response body, the URL or the exception text is kept, so a key cannot leak through an
error, a log line or the stored row."""
from __future__ import annotations

from typing import Any, Optional

import httpx

TIMEOUT_SECONDS = 5.0
ERROR_CODES = ("timeout", "network", "unauthorized", "not_found", "rate_limited", "http_error", "bad_response",
               "graphql_error")


class ProviderError(Exception):
    def __init__(self, code: str, http_status: Optional[int] = None, retry_after: Optional[int] = None):
        assert code in ERROR_CODES, code
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.retry_after = retry_after

    def stored(self) -> str:
        """The `infra_snapshots.error` value: the code, and the HTTP status when there is one."""
        return f"{self.code}:{self.http_status}" if self.http_status else self.code


def _retry_after(value: Optional[str]) -> Optional[int]:
    try:
        return max(0, int(value)) if value is not None else None
    except ValueError:
        return None


def request_json(client: httpx.Client, method: str, url: str, *, headers: dict, params: Optional[dict] = None,
                 json: Any = None) -> Any:
    try:
        r = client.request(method, url, headers=headers, params=params, json=json)
    except httpx.TimeoutException:
        raise ProviderError("timeout") from None
    except httpx.HTTPError:
        raise ProviderError("network") from None
    status = r.status_code
    if status in (401, 403):
        raise ProviderError("unauthorized", status)
    if status == 404:
        raise ProviderError("not_found", status)
    if status == 429:
        raise ProviderError("rate_limited", status, _retry_after(r.headers.get("retry-after")))
    if status >= 400:
        raise ProviderError("http_error", status)
    try:
        return r.json()
    except ValueError:
        raise ProviderError("bad_response", status) from None


def obj(value: Any) -> dict:
    if not isinstance(value, dict):
        raise ProviderError("bad_response")
    return value


def opt_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderError("bad_response")
    return int(value)


def opt_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProviderError("bad_response")
    return float(value)


def opt_str(value: Any, max_len: int = 64) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProviderError("bad_response")
    return value[:max_len]
