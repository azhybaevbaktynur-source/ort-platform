"""Cloudflare R2: operations and stored bytes this month from the GraphQL Analytics API (INFRA_PANEL_DESIGN 2, D-I5-2).
One POST per refresh carrying both datasets. The token needs Account Analytics Read only."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import httpx

from app.core.config import settings
from app.lms.core import clock
from app.lms.infra.providers import ProviderError, obj, opt_int, request_json

NAME = "r2"
GRAPHQL = "https://api.cloudflare.com/client/v4/graphql"
FREE_STORAGE_BYTES = 10_000_000_000  # 10 GB decimal (https://developers.cloudflare.com/r2/pricing/)
FREE_CLASS_A = 1_000_000
FREE_CLASS_B = 10_000_000

# https://developers.cloudflare.com/r2/pricing/ (2026-11-09). Anything else (deletes, aborts) is free.
CLASS_A = frozenset({
    "ListBuckets", "PutBucket", "ListObjects", "PutObject", "CopyObject", "CompleteMultipartUpload",
    "CreateMultipartUpload", "LifecycleStorageTierTransition", "ListMultipartUploads", "UploadPart", "UploadPartCopy",
    "ListParts",
})
CLASS_B = frozenset({"HeadBucket", "HeadObject", "GetObject", "UsageSummary"})
_PUT_CONFIG = re.compile(r"^PutBucket\w+$")  # PutBucketEncryption, PutBucketCors, PutBucketLifecycleConfiguration
_GET_CONFIG = re.compile(r"^GetBucket\w+$")  # GetBucketEncryption, GetBucketLocation, GetBucketCors, ...

QUERY = """query R2Usage($accountTag: string!, $start: Date!) {
  viewer {
    accounts(filter: {accountTag: $accountTag}) {
      ops: r2OperationsAdaptiveGroups(limit: 10000, filter: {date_geq: $start}) {
        sum { requests }
        dimensions { actionType actionStatus bucketName }
      }
      storage: r2StorageAdaptiveGroups(limit: 100, filter: {date_geq: $start}, orderBy: [datetime_DESC]) {
        max { payloadSize metadataSize objectCount }
        dimensions { datetime bucketName }
      }
    }
  }
}"""


@dataclass(frozen=True)
class R2Usage:
    month_start: str
    class_a: int
    class_b: int
    stored_bytes: Optional[int]
    object_count: Optional[int]
    buckets: int


def classify(action: str) -> Optional[str]:
    """"A", "B" or None (free) for an R2 actionType."""
    if action in CLASS_A or _PUT_CONFIG.match(action):
        return "A"
    if action in CLASS_B or _GET_CONFIG.match(action):
        return "B"
    return None


def account_id() -> str:
    return settings.CLOUDFLARE_ACCOUNT_ID or settings.R2_ACCOUNT_ID


def connection() -> str:
    return "connected" if settings.CLOUDFLARE_API_TOKEN and account_id() else "not_connected"


def dashboard_url() -> str:
    acct = account_id()
    return f"https://dash.cloudflare.com/{acct}/r2/overview" if acct else "https://dash.cloudflare.com/"


def fetch(client: httpx.Client) -> R2Usage:
    start = clock.now().date().replace(day=1).isoformat()
    headers = {"Authorization": f"Bearer {settings.CLOUDFLARE_API_TOKEN}", "Content-Type": "application/json"}
    body = obj(request_json(client, "POST", GRAPHQL, headers=headers,
                            json={"query": QUERY, "variables": {"accountTag": account_id(), "start": start}}))
    if body.get("errors"):
        raise ProviderError("graphql_error")
    accounts = obj(obj(body.get("data")).get("viewer")).get("accounts")
    if not isinstance(accounts, list) or len(accounts) != 1:
        raise ProviderError("bad_response")
    acct = obj(accounts[0])
    ops, storage = acct.get("ops"), acct.get("storage")
    if not isinstance(ops, list) or not isinstance(storage, list):
        raise ProviderError("bad_response")
    totals = {"A": 0, "B": 0}
    for g in ops:
        g = obj(g)
        action = obj(g.get("dimensions")).get("actionType")
        cls = classify(action) if isinstance(action, str) else None
        if cls:
            totals[cls] += opt_int(obj(g.get("sum")).get("requests")) or 0
    latest: dict[str, dict] = {}  # rows come newest first: the first row per bucket is its current size
    for g in storage:
        g = obj(g)
        bucket = obj(g.get("dimensions")).get("bucketName")
        if isinstance(bucket, str) and bucket not in latest:
            latest[bucket] = obj(g.get("max"))
    stored = sum((opt_int(m.get("payloadSize")) or 0) + (opt_int(m.get("metadataSize")) or 0) for m in latest.values())
    objects = sum(opt_int(m.get("objectCount")) or 0 for m in latest.values())
    return R2Usage(month_start=start, class_a=totals["A"], class_b=totals["B"],
                   stored_bytes=stored if latest else None, object_count=objects if latest else None,
                   buckets=len(latest))
