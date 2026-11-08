#!/usr/bin/env python3
"""A tiny stand-in for Google's OAuth endpoints, for the browser e2e suite only (docs/phases/AUTH_SOCIAL_DESIGN.md 9).

`scripts/e2e_backend.sh` starts it on 127.0.0.1 and points the backend's GOOGLE_OAUTH_{AUTHORIZE,TOKEN,JWKS}_URL and
GOOGLE_OAUTH_ISSUERS at it (production refuses to start with those changed: config.refuse_unsafe_oauth_urls).

Endpoints
  GET  /authorize  immediate 302 back to `redirect_uri` with `code` and `state` (no page). The person "signing in" is,
                   in this order: the query parameters `email`, `email_verified` (true | false | missing), `name`, `sub`
                   added to /authorize (a spec can add them with page.route), else the identity queued by the last
                   GET /next, else a fresh default person. `deny=1` (either place) answers `error=access_denied`.
  GET  /next       queues the identity for the next /authorize (same parameters); answers 204.
  POST /token      checks the code (single use), client id and secret, redirect_uri and the PKCE verifier; answers an
                   RS256 ID token with the nonce of the flow.
  GET  /certs      the JWKS.
The RSA key is generated at start and never written anywhere. The client secret comes from E2E_OAUTH_CLIENT_SECRET (a
throwaway value e2e_backend.sh generates per run).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa

IDENTITY_KEYS = ("email", "email_verified", "name", "sub", "deny")


class Stub:
    def __init__(self, issuer: str, client_id: str, client_secret: str, redirect_uri: str):
        self.issuer, self.client_id, self.client_secret, self.redirect_uri = issuer, client_id, client_secret, redirect_uri
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.kid = "e2e-" + secrets.token_hex(4)
        self.lock = threading.Lock()
        self.codes: dict[str, dict] = {}
        self.next_identity: dict[str, str] = {}

    def jwks(self) -> dict:
        jwk = jwt.algorithms.RSAAlgorithm.to_jwk(self.key.public_key(), as_dict=True)
        return {"keys": [{**jwk, "kid": self.kid, "alg": "RS256", "use": "sig"}]}

    def identity(self, query: dict[str, str]) -> dict[str, str]:
        chosen = {k: query[k] for k in IDENTITY_KEYS if k in query}
        if not chosen:
            with self.lock:
                chosen, self.next_identity = self.next_identity, {}
        return chosen

    def claims(self, person: dict[str, str], nonce: str) -> dict:
        now = int(time.time())
        email = person.get("email") or f"e2e-{secrets.token_hex(4)}@gmail.test"
        out = {"iss": self.issuer, "aud": self.client_id, "sub": person.get("sub") or "e2e-" + hashlib.sha256(
            email.encode()).hexdigest()[:20], "iat": now, "exp": now + 3600, "nonce": nonce, "email": email,
            "name": person.get("name") or "E2E Person"}
        verified = (person.get("email_verified") or "true").lower()
        if verified != "missing":
            out["email_verified"] = verified in ("true", "1", "yes")
        return out


def make_handler(stub: Stub):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # quiet; the e2e logs stay readable
            pass

        def _send(self, status: int, body: dict | None = None, headers: dict | None = None):
            data = json.dumps(body).encode() if body is not None else b""
            self.send_response(status)
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            if body is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            url = urlparse(self.path)
            query = {k: v[0] for k, v in parse_qs(url.query).items()}
            if url.path == "/certs":
                return self._send(200, stub.jwks())
            if url.path == "/next":
                with stub.lock:
                    stub.next_identity = {k: query[k] for k in IDENTITY_KEYS if k in query}
                return self._send(204)
            if url.path == "/authorize":
                if query.get("redirect_uri") != stub.redirect_uri or query.get("client_id") != stub.client_id:
                    return self._send(400, {"error": "invalid_request"})
                person = stub.identity(query)
                back = {"state": query.get("state", "")}
                if person.get("deny"):
                    back["error"] = "access_denied"
                else:
                    code = secrets.token_urlsafe(24)
                    with stub.lock:
                        stub.codes[code] = {"challenge": query.get("code_challenge", ""),
                                            "claims": stub.claims(person, query.get("nonce", ""))}
                    back["code"] = code
                return self._send(302, headers={"Location": f"{stub.redirect_uri}?{urlencode(back)}"})
            return self._send(404, {"error": "not_found"})

        def do_POST(self):
            if urlparse(self.path).path != "/token":
                return self._send(404, {"error": "not_found"})
            length = min(int(self.headers.get("Content-Length") or 0), 64 * 1024)
            form = {k: v[0] for k, v in parse_qs(self.rfile.read(length).decode()).items()}
            with stub.lock:
                entry = stub.codes.pop(form.get("code", ""), None)
            if (form.get("client_id") != stub.client_id or form.get("client_secret") != stub.client_secret):
                return self._send(401, {"error": "invalid_client"})
            if entry is None or form.get("redirect_uri") != stub.redirect_uri:
                return self._send(400, {"error": "invalid_grant"})
            challenge = base64.urlsafe_b64encode(hashlib.sha256(form.get("code_verifier", "").encode()).digest())
            if challenge.decode().rstrip("=") != entry["challenge"]:
                return self._send(400, {"error": "invalid_grant"})
            token = jwt.encode(entry["claims"], stub.key, algorithm="RS256", headers={"kid": stub.kid})
            return self._send(200, {"id_token": token, "token_type": "Bearer", "expires_in": 3600})

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--redirect-uri", required=True, help="the backend's /api/v1/auth/google/callback")
    args = parser.parse_args()
    secret = os.environ.get("E2E_OAUTH_CLIENT_SECRET", "")
    if not secret:
        raise SystemExit("e2e_oauth_stub: set E2E_OAUTH_CLIENT_SECRET")
    issuer = f"http://127.0.0.1:{args.port}"
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Stub(issuer, args.client_id, secret,
                                                                              args.redirect_uri)))
    print(f"e2e_oauth_stub: listening on {issuer}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
