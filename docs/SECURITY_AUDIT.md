# Security audit (Phase 11 S4)

Design: `docs/phases/PHASE_11_DESIGN.md` §5. Runbook for IP limits: `docs/runbooks/IP_CHAIN.md`. The full `/security-review` is a later gate (design §12).

## Dependencies

CI job `audit` runs both checks on every push; `.github/dependabot.yml` opens weekly update PRs. Last run: 2026-11-02.

| Check | Result |
|---|---|
| `pip-audit -r backend/requirements.txt` | No known vulnerabilities |
| `npm audit --omit=dev --audit-level=high` | Passes; one low finding, accepted below |

**Fixed in S4** (patch-level, proven by build and ORT pixel baselines):

| Package | From | To | Advisory |
|---|---|---|---|
| `next` | 15.5.26 | 15.5.28 | Critical: GHSA-2464-fhr4-w9xw (image optimizer RCE), GHSA-4jqv-mc3x-m676 and GHSA-mcj8-r9mp-w47p (cache poisoning), GHSA-p3m5-59mp-jv5r (Server Actions DoS) |
| `sharp` | 0.35.4 | 0.35.5 | High: GHSA-wq5f-xc86-pv6w |
| `source-map-js` | 1.2.1 | 1.2.2 | High: GHSA-68fv-2mgg-jv7q |
| `postcss` inside `next` | 8.4.31 | 8.5.28 | High: GHSA-qx2v-qp2m-jg93 and others. By `overrides` in `package.json`: Next pins it exactly, and the only upstream fix is Next 16 (breaking). Build-time only, on our own CSS. Remove the override when Next moves past it. |

**Accepted**:

| Finding | Severity | Why accepted | Revisit |
|---|---|---|---|
| `katex` 0.16.47, GHSA-238p-pmpm-9mq7 (prototype pollution can bypass `trust`) | Low | Needs an existing prototype pollution, and the app has no known source. The fix is a major version (0.19), and KaTeX draws every ORT formula, so it needs the ORT pixel gate rather than a security patch. | Next deliberate upgrade with the ORT baselines |

## Content Security Policy

Set in `frontend/next.config.ts`, enforced on every page, not on the `/api` rewrite. `frontend/e2e/helpers.ts` fails any test that logs a violation, so the ORT, visual and player specs prove the player still works. `frontend/e2e/security.spec.ts` proves the watcher itself and the rest.

**Deliberate limits**:
- `'unsafe-inline'` in `script-src`: nonces force dynamic rendering on every page and spend the free function allowance.
- `https://*.r2.dev` in `img-src` and `connect-src`, wider than one bucket: public images come from an r2.dev address until the owner buys a domain, and images must not depend on a Vercel variable being set.
- API origin in `img-src` (not in the design): images come from `/api/v1/media` without R2.

**Before moving images to a custom domain**: set `NEXT_PUBLIC_R2_PUBLIC_BASE_URL` on Vercel and redeploy the frontend, **then** change `R2_PUBLIC_BASE_URL` on Render. In the other order, students see no images.

## `dangerouslySetInnerHTML` review

Reviewed 2026-11-02. All five render sanitized output only; none changed.

| File | Source | Finding |
|---|---|---|
| `components/math/MathRenderer.tsx` | `renderRichText` | Text is escaped first, then only `<u>` and `<b>` come back. Math goes through KaTeX with `trust: false`. |
| `components/lms/PlainPassage.tsx`, `NumberedPassage.tsx` | `renderRichText` per line | As above. |
| `components/lms/quiz/QuestionCard.tsx` | `renderRichText` | As above. |
| `components/lms/pages/SafeHtml.tsx` | Server `body_html` | `nh3` allow-list on the server; KaTeX auto-render with `trust: false` on top. |

## Sessions

**HttpOnly cookies: no, stay on Bearer** (design §5.4, recorded in `PRODUCT_DECISIONS.md`). The compensation is 3-day rolling tokens, revocation, the CSP and the server sanitizer. Revisit with a custom domain.

- **Rolling**: `POST /auth/refresh`; `<TokenRefresh/>` swaps a token older than 12 h on any page except the player. Tokens issued before this release (7 days, no `tv`, no `iat`) stay valid until they expire.
- **Revocation**: `users.token_version`, bumped by reset-password, `POST /auth/logout-all`, admin disable and anonymize. Enabling an account again does not revive old tokens.
- **Rotation** (owner, not done): set `SECRET_KEY_PREVIOUS` to the current key and `SECRET_KEY` to a new one, deploy, remove the previous key after 3 days. Login tokens survive. These do not, which is acceptable for a rare rotation: reset links and email codes in flight (up to 1 hour; ask again), and the counts of IP buckets (they restart from zero, because the address hash is keyed).

## Accepted risks

| Risk | Why accepted |
|---|---|
| A password reset or logout-all during an exam ends that exam tab's token | Only the account's own owner can do either. The attempt client keeps its queue on 401 and asks to sign in, so answers are not lost. |
| Anyone who knows a student's email can block that student's **login** for 10 minutes (10 wrong passwords), and spend their reset emails for an hour (5 requests) | Inherent to per-account limits, which are what stop guessing. It cannot touch a session already open or an exam in progress. No kill switch: these are not IP rules. Watch the logs. |
| A rolling token can be refreshed for as long as it stays valid | The session ends on revocation. An absolute cap would log out active students on a schedule, possibly mid-term. |
| `GET /invitations/{token}` accepts a revoked token as an identity | It only selects a per-user rate-limit bucket on a public route; accepting an invitation uses `get_lms_user`, which checks revocation. |
| Same-origin Vercel path stays open | See `docs/runbooks/IP_CHAIN.md`. |

## Test-student files

`POST /admin/storage/test-student-files/sweep` (platform admin, `{apply: false}` by default) reports or erases hand-in files of retired test students, 200 per run; repeat until `files` is 0. **Applying on production needs the owner's first OK** (design invariant 6). Not run on production.
