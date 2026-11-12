"""Error codes of the course listing (CATALOG_AND_TEACHERS_DESIGN 4.2)."""
E_LISTING_INCOMPLETE = "listing_incomplete"      # 422, details: the missing items (`LISTING_MISSING`)
E_LISTING_STATE = "listing_state"                # 409, wrong transition for the current state
E_LISTING_BLOCKED = "listing_blocked"            # 409, blocked by the platform admin: staff cannot request
E_LISTING_RATE_LIMITED = "listing_rate_limited"  # 429
E_LISTING_NOTE_REQUIRED = "listing_note_required"  # 422, decline without a note
E_LISTING_NOT_ALLOWED = "listing_not_allowed"    # 409, a template-locked (ORT) course: the platform lists it

LISTING_STATES = ("off", "pending", "listed", "declined", "blocked")
# what `listing_incomplete` names (D11): published, link access, title and description in the default language,
# a cover or at least one published test or lesson
LISTING_MISSING = ("published", "link_access", "title", "description", "cover_or_content")
