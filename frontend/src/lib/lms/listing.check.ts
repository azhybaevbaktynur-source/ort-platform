/**
 * Step 3b S2: the catalog listing rules of the course settings, checked without a browser (like `roleLinks.check.ts`).
 * Run: cd frontend && npx tsc --outDir /tmp/agy_listing --module commonjs --target es2020 --skipLibCheck \
 *   src/lib/lms/listing.ts src/lib/lms/listing.check.ts && node /tmp/agy_listing/listing.check.js
 */
import { LISTING_MISSING, listingActions, listingMissing, missingFromError } from "./listing";

let failed = 0;
function ok(cond: boolean, msg: string) {
  if (!cond) { failed++; console.error("FAIL", msg); } else console.log("ok  ", msg);
}
const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const ready = {
  status: "published" as const, visibility: "catalog" as const, default_language: "ru" as const,
  title: { ru: "Алгебра" }, description: { ru: "Курс" } as { ru?: string } | null, cover_url: null as string | null,
  features: { modules: true, files: false, announcements: false, tests: false, hand_ins: false } as
    { modules: boolean; files: boolean; announcements: boolean; tests: boolean; hand_ins: boolean } | undefined,
};
ok(same(listingMissing(ready), []), "a ready course misses nothing");
ok(same(listingMissing({ ...ready, status: "draft", visibility: "private" }), ["published", "link_access"]), "draft and private");
ok(same(listingMissing({ ...ready, title: { ru: "  ", en: "Algebra" } as { ru: string } }), ["title"]), "title only in another language");
ok(same(listingMissing({ ...ready, description: null }), ["description"]), "no description");
const bare = { modules: false, files: true, announcements: true, tests: false, hand_ins: false };
ok(same(listingMissing({ ...ready, features: bare }), ["cover_or_content"]), "files and announcements are not content");
ok(same(listingMissing({ ...ready, features: bare, cover_url: "https://x/c.webp" }), []), "a cover is enough");
ok(same(listingMissing({ ...ready, features: { ...bare, hand_ins: true } }), []), "a hand-in is content");
ok(same(listingMissing({ ...ready, features: { ...bare, tests: true } }), []), "a test is content");
ok(same(listingMissing({ ...ready, features: undefined }), []), "unknown content: the server decides");
ok(same(listingMissing({ ...ready, status: "draft", description: {}, features: bare }),
  ["published", "description", "cover_or_content"]), "LISTING_MISSING order");

ok(same(missingFromError({ code: "listing_incomplete", details: { missing: ["cover_or_content", "title", "x"] } }), ["title", "cover_or_content"]),
  "the server's list, known items in order");
ok(missingFromError({ code: "listing_state" }) === null && missingFromError(null) === null, "other errors are not a missing list");
ok(same(missingFromError({ code: "listing_incomplete" }), []), "no details: an empty list");

ok(same(listingActions("off"), ["request"]) && same(listingActions("pending"), ["withdraw"])
  && same(listingActions("listed"), ["remove"]) && same(listingActions("declined"), ["resend"]), "one action per state");
ok(listingActions("blocked").length === 0, "a blocked course has no button");
ok(LISTING_MISSING.length === 5, "five missing items (ids.LISTING_MISSING)");

if (failed) {
  console.error(`${failed} failed`);
  process.exit(1);
}
console.log("all ok");
