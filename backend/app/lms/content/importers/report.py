"""Dry-run report builder (design section 5 shape). Pure: without a plan every row counts as `created`."""
from __future__ import annotations

from typing import Optional

from .bundle import display_root
from .parsed import ParsedBundle, ParsedUpload
from .schemas import ImportBankSummary, ImportReport


def section_counts(bundle: ParsedBundle) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in bundle.items:
        out[it.section] = out.get(it.section, 0) + 1
    return out


def build_report(up: ParsedUpload, *, committed: bool = False,
                 plan: Optional[dict[str, dict]] = None) -> ImportReport:
    """`plan` (writer, step 2) maps bundle root -> summary field overrides
    (bank_id, bank_exists, created, updated, unchanged, conflicts, skipped_deleted)."""
    banks: list[ImportBankSummary] = []
    for b in up.bundles:
        secs = section_counts(b)
        s = ImportBankSummary(
            root=display_root(b.root) if up.kind == "zip" else "",
            source_id=b.source_id, has_manifest=b.has_manifest, language=b.language, bank_title=b.title,
            question_count=len(b.items), sections=secs, created=dict(secs),
            images=len({i.source_sha256 for i in b.images.values()}),
        )
        if plan and b.root in plan:
            s = s.model_copy(update=plan[b.root])
        banks.append(s)
    total = len(up.distinct_images)
    return ImportReport(
        ok=not up.issues.errors, committed=committed and not up.issues.errors, banks=banks,
        errors=list(up.issues.errors), warnings=list(up.issues.warnings),
        images_total=total, images_new=total, images_existing=0,
    )
