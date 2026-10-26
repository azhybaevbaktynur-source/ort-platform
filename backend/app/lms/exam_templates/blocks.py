"""Building-block constants (PHASE_7B_DESIGN 7, EXAM_TEMPLATES_DESIGN 4). S1 defines the key lists used for
validation; S2 adds `catalog(db, ctx) -> BlocksOut` for `GET /exam-templates/blocks`. The frontend mirror is
`frontend/src/lib/lms/blocks.ts` (`tests/lms/test_blocks_contract.py` compares both)."""
from __future__ import annotations

RESULT_VIEWS = ("general", "ort")
PASSAGE_DISPLAYS = ("plain", "numbered")
DISPLAY_MODES = ("one_per_page", "scrolling")
NAVIGATIONS = ("free", "section_forward_only")
IMPORTER_PROFILES = ("general", "ort")
# The importer profile a spec may name; "ort" is reserved for the ORT course template (4.4).
SPEC_IMPORTER_PROFILES = ("general",)


# --- Phase 7b S2 begin --- (PHASE_7B_DESIGN 7: the catalog endpoint; the SQL lives in service.blocks)
def catalog(db, ctx):
    """`GET /exam-templates/blocks` payload for `ctx` (the scheme list is the caller's: system + own)."""
    from app.lms.exam_templates import service

    return service.blocks(ctx)
# --- Phase 7b S2 end ---
