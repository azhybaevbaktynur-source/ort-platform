"""F6a Pro settings (docs/phases/SUBSCRIPTION_DESIGN.md 2, 3): the owner's season end, plan prices and "how to pay"
texts, one `platform_settings` row per key. Owner 2026-11-07: prices and the season end are not decided, so everything
is nullable and nothing is inserted until the admin saves: no season end → no season plan; no price → no price shown.

Keys: `pro_season_end` `{"date": "2027-05-31" | null}`, `pro_prices` `{"month_1": 990 | null, ...}` (KGS),
`pro_how_to_pay` `{"ru": "...", "ky": "...", "en": "..."}`. Read time: an empty ky/en text falls back to ru; an empty
ru text stays empty and the page shows the i18n placeholder `access.howToPay`."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.lms.access.models import PlatformSetting
from app.lms.access.plans import PLAN_IDS
from app.lms.audit import service as audit
from app.lms.core import clock
from app.lms.core.errors import ValidationFailed
from app.models.user import User

KEY_SEASON_END = "pro_season_end"
KEY_PRICES = "pro_prices"
KEY_HOW_TO_PAY = "pro_how_to_pay"
KEYS = (KEY_SEASON_END, KEY_PRICES, KEY_HOW_TO_PAY)
LANGS = ("ru", "ky", "en")
MAX_PRICE = 1_000_000
MAX_TEXT = 2000
SEASON_MAX_DAYS = 400  # the season plan never breaks the grant cap
AUDIT_SETTINGS = "access.settings_update"


@dataclass(frozen=True)
class ProSettings:
    season_end: Optional[date] = None
    prices: dict = field(default_factory=lambda: {p: None for p in PLAN_IDS})
    how_to_pay: dict = field(default_factory=lambda: {lang: "" for lang in LANGS})

    def as_json(self) -> dict:
        return {"season_end": self.season_end.isoformat() if self.season_end else None,
                "prices": dict(self.prices), "how_to_pay": dict(self.how_to_pay)}

    def how_to_pay_with_fallback(self) -> dict:
        ru = self.how_to_pay.get("ru") or ""
        return {lang: (self.how_to_pay.get(lang) or ru) for lang in LANGS}


def _invalid(msg: str, **details) -> ValidationFailed:
    return ValidationFailed(msg, code="settings_invalid", details=details or None)


def _parse(rows: dict[str, Any]) -> ProSettings:
    """Stored rows → settings; anything unreadable reads as unset (the owner saves again)."""
    season_end = None
    raw = (rows.get(KEY_SEASON_END) or {}).get("date") if isinstance(rows.get(KEY_SEASON_END), dict) else None
    if isinstance(raw, str):
        try:
            season_end = date.fromisoformat(raw)
        except ValueError:
            season_end = None
    stored_prices = rows.get(KEY_PRICES) if isinstance(rows.get(KEY_PRICES), dict) else {}
    prices = {}
    for p in PLAN_IDS:
        v = stored_prices.get(p)
        prices[p] = v if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= MAX_PRICE else None
    stored_texts = rows.get(KEY_HOW_TO_PAY) if isinstance(rows.get(KEY_HOW_TO_PAY), dict) else {}
    texts = {lang: (stored_texts.get(lang) if isinstance(stored_texts.get(lang), str) else "") for lang in LANGS}
    return ProSettings(season_end=season_end, prices=prices, how_to_pay=texts)


def _load(db: Session, *, for_update: bool = False) -> dict[str, Any]:
    stmt = select(PlatformSetting.key, PlatformSetting.value).where(PlatformSetting.key.in_(KEYS))
    if for_update:
        stmt = stmt.with_for_update()
    return {k: v for k, v in db.execute(stmt).all()}


def get_pro(db: Session) -> ProSettings:
    """One statement."""
    return _parse(_load(db))


def validate(*, season_end: Optional[date], prices: dict, how_to_pay: dict, today: date,
             check_season: bool = True) -> ProSettings:
    if check_season and season_end is not None and not (
            today <= season_end <= today + timedelta(days=SEASON_MAX_DAYS)):
        raise _invalid("The season end must be between today and 400 days from now", field="season_end")
    unknown = set(prices) - set(PLAN_IDS)
    if unknown:
        raise _invalid("Unknown plan", field="prices")
    clean_prices = {}
    for p in PLAN_IDS:
        v = prices.get(p)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 0 <= v <= MAX_PRICE):
            raise _invalid("A price is a whole number from 0 to 1,000,000", field="prices", plan=p)
        clean_prices[p] = v
    if set(how_to_pay) - set(LANGS):
        raise _invalid("Unknown language", field="how_to_pay")
    texts = {}
    for lang in LANGS:
        v = how_to_pay.get(lang)
        v = "" if v is None else v
        if not isinstance(v, str) or len(v) > MAX_TEXT:
            raise _invalid("At most 2000 characters", field="how_to_pay", lang=lang)
        texts[lang] = v.strip()
    return ProSettings(season_end=season_end, prices=clean_prices, how_to_pay=texts)


def _upsert(db: Session, key: str, value: dict, admin_id: str, now) -> None:
    t = PlatformSetting.__table__
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    stmt = insert(t).values(key=key, value=value, updated_at=now, updated_by_id=admin_id)
    db.execute(stmt.on_conflict_do_update(index_elements=[t.c.key],
                                          set_={"value": value, "updated_at": now, "updated_by_id": admin_id}))


def put_pro(db: Session, admin: User, patch: dict, request: Optional[Request] = None) -> ProSettings:
    """`patch`: only the keys the admin sent (`season_end`, `prices.<plan>`, `how_to_pay.<lang>`); a missing key keeps
    the stored value, an explicit null clears it. Validates the merged result (the season end only when sent, so a
    stored end that has passed does not block saving a price), upserts the three rows in one transaction and audits
    old/new (only when something changed)."""
    from app.lms.access.service import bishkek_today

    now = clock.now()
    old = _parse(_load(db, for_update=True))
    if set(patch) - {"season_end", "prices", "how_to_pay"}:
        raise _invalid("Unknown setting")
    prices = {**old.prices, **(patch.get("prices") or {})}
    texts = {**old.how_to_pay, **(patch.get("how_to_pay") or {})}
    try:
        new = validate(season_end=patch["season_end"] if "season_end" in patch else old.season_end, prices=prices,
                       how_to_pay=texts, today=bishkek_today(now), check_season="season_end" in patch)
    except ValidationFailed:
        db.rollback()
        raise
    if old.as_json() == new.as_json():
        db.rollback()
        return new
    values = {KEY_SEASON_END: {"date": new.season_end.isoformat() if new.season_end else None},
              KEY_PRICES: dict(new.prices), KEY_HOW_TO_PAY: dict(new.how_to_pay)}
    for key, value in values.items():
        _upsert(db, key, value, admin.id, now)
    audit.record(db, actor=admin, action=AUDIT_SETTINGS, target_type="platform_setting", target_id="pro",
                 details={"old": old.as_json(), "new": new.as_json()}, request=request)
    db.commit()
    return new
