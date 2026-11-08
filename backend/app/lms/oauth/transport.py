"""Outbound HTTP to the identity providers and their signing keys (AUTH_SOCIAL_DESIGN 1.3 steps 5-6, 9).

Every call to Google or Apple goes through `http_client()`, so the tests (and nothing else) swap it for an
`httpx.MockTransport`. 8 s timeout, no retries: a provider outage fails the sign-in fast and password login is unaffected.
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional

import httpx
import jwt

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 8.0
JWKS_LIFESPAN_SECONDS = 21600  # 6 h; a provider's JWKS outage is survived for this long


class OAuthFailure(Exception):
    """A refusal with the code the frontend translates (`auth.errors.<code>`)."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def http_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def post_form(url: str, data: dict) -> dict:
    """POST a form to a token endpoint; the JSON answer or OAuthFailure. The body is never logged (it can hold tokens)."""
    try:
        with http_client() as client:
            res = client.post(url, data=data, headers={"Accept": "application/json"})
    except httpx.HTTPError as exc:
        logger.warning("oauth token endpoint unreachable", extra={"error": type(exc).__name__})
        raise OAuthFailure("oauth_provider_error") from None
    if res.status_code != 200:
        logger.warning("oauth token endpoint refused", extra={"status_code": res.status_code})
        raise OAuthFailure("oauth_provider_error")
    try:
        body = res.json()
    except ValueError:
        raise OAuthFailure("oauth_provider_error") from None
    if not isinstance(body, dict):
        raise OAuthFailure("oauth_provider_error")
    return body


class JwksCache:
    """The provider's public keys by `kid`, refreshed every 6 h; an unknown `kid` fetches again at most once per call
    (a key rotation at the provider)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._keys: dict[str, jwt.PyJWK] = {}
        self._url: Optional[str] = None
        self._fetched_at = 0.0

    def clear(self) -> None:
        with self._lock:
            self._keys, self._url, self._fetched_at = {}, None, 0.0

    def _fetch(self, url: str) -> None:
        try:
            with http_client() as client:
                res = client.get(url, headers={"Accept": "application/json"})
            res.raise_for_status()
            keys = {}
            for data in res.json().get("keys", []):
                if not isinstance(data, dict) or not data.get("kid"):
                    continue
                try:
                    keys[str(data["kid"])] = jwt.PyJWK(data)
                except jwt.PyJWTError:
                    continue  # a key type we do not use
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            logger.warning("oauth signing keys unavailable", extra={"error": type(exc).__name__})
            if self._url == url and self._keys:
                return  # keep the cached keys through an outage
            raise OAuthFailure("oauth_provider_error") from None
        self._keys, self._url, self._fetched_at = keys, url, time.monotonic()

    def key(self, url: str, kid: Optional[str]) -> jwt.PyJWK:
        if not kid:
            raise OAuthFailure("oauth_provider_error")
        with self._lock:
            fetched = False
            if self._url != url or time.monotonic() - self._fetched_at > JWKS_LIFESPAN_SECONDS:
                self._fetch(url)
                fetched = True
            if kid not in self._keys and not fetched:
                self._fetch(url)
            found = self._keys.get(kid)
        if found is None:
            raise OAuthFailure("oauth_provider_error")
        return found
