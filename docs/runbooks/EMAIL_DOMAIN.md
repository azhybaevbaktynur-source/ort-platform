# Email from our own domain (Brevo + Cloudflare Email Routing)

Owner round 2026-11-13, item 6. Today the platform sends from the owner's personal address (set in Render's env, never
in the repository). This runbook moves sending to `noreply@<domain>` and forwards `support@<domain>` to the owner's
inbox. **Do not start until the owner has given the domain and the platform name.** Placeholders: `<domain>` (for example
`example.kg`, no `www`), `<platform name>`, `<owner inbox>` (the owner's personal address, never written into the repo).

Part of the domain switch in `CUSTOM_DOMAIN.md` (step 6 there). Prerequisite: the domain's DNS is on Cloudflare
(`CUSTOM_DOMAIN.md` step 1); Email Routing only works with Cloudflare DNS.

## How the code picks the sender (no code change needed for the switch)

One helper, `app/services/email_service.py`: `sender_address()` and `sender_name()`, used by Brevo, Resend, SMTP and the
console log, for every email (registration code, password reset, email change, security notices, invitations, enrollment
forms, teacher applications, catalog listing).

| Variable (Render env) | Meaning |
|---|---|
| `EMAIL_PROVIDER` | `brevo` (production), `resend`, `smtp` (blocked on Render free) or `console` (dev log only). Empty = picked from the keys that are set. |
| `BREVO_API_KEY` | Brevo → SMTP & API → API keys. Secret. |
| `EMAIL_FROM` | The From address. Must be a sender or domain verified in Brevo. |
| `EMAIL_FROM_NAME` | The From name. Leave it **unset or `Platform`** to get the per-language platform name in auth emails (`APP_NAME` in `email_service.py`, same as `common.appName` in the dictionaries); any other value is used as-is for every email. Invitations use "<inviter> via <platform name>". |
| `SMTP_FROM_EMAIL` | Legacy alias of `EMAIL_FROM`, read only when `EMAIL_FROM` is empty. Default empty (it used to be a made-up domain). |
| `SMTP_USER` | Last fallback for the address (SMTP login). |

If none of the three address variables is set, nothing is sent: the request answers as an email failure, the log says
`EMAIL_FROM is not set`, and Admin → Services shows email as not configured. There is no built-in domain default, so a
fresh server can never send from a domain nobody verified.

## 1. Authenticate `<domain>` in Brevo (owner: Brevo and Cloudflare dashboards)

Brevo → **Senders, domains & dedicated IPs → Domains → Add a domain** → `<domain>` → choose to configure the records
manually (or "Authenticate automatically" if Brevo offers Cloudflare; then skip to the check). Brevo shows the exact
values; **copy them from the Brevo dashboard**, the ones below are the shape only. In Cloudflare → `<domain>` → DNS →
Records, add each one with **Proxy status: DNS only** (CNAME records for mail must not be proxied):

| Type | Name (Cloudflare adds `.<domain>`) | Value |
|---|---|---|
| TXT | `@` | `brevo-code:<code from Brevo>` (proves ownership) |
| CNAME | `brevo1._domainkey` | `b1.<domain with dots as dashes>.dkim.brevo.com` (DKIM key 1) |
| CNAME | `brevo2._domainkey` | `b2.<domain with dots as dashes>.dkim.brevo.com` (DKIM key 2) |
| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` (see step 3) |

DKIM: Brevo's current form is the two CNAME records above (Brevo rotates the keys behind them). Older Brevo accounts
show a single TXT record instead: name `mail._domainkey`, value `k=rsa;p=<long key>`. Use whichever the dashboard shows,
not both.

Then **Authenticate this email domain** in Brevo. Cloudflare DNS usually answers within minutes; Brevo says up to 24–48 h.
Check from a terminal: `dig +short TXT <domain>`, `dig +short CNAME brevo1._domainkey.<domain>`, `dig +short TXT _dmarc.<domain>`.

Verify: Brevo → Domains shows `<domain>` with Brevo code, DKIM and DMARC all green.
Rollback: delete the records; nothing else depends on them yet.

## 2. SPF: one record for Brevo and Cloudflare

A domain may have **only one** `v=spf1` TXT record (a second one makes SPF fail with "permerror"). Brevo itself says SPF
is not needed to authenticate a domain on its shared IPs: Brevo's own bounce domain is the envelope sender, and DMARC
passes through the aligned DKIM signature. Adding Brevo's include is harmless and covers a later dedicated IP, so we
publish one merged record:

| Type | Name | Value |
|---|---|---|
| TXT | `@` | `v=spf1 include:_spf.mx.cloudflare.net include:spf.brevo.com ~all` |

`_spf.mx.cloudflare.net` is the include Cloudflare Email Routing adds (step 4). If Email Routing is set up first, edit
its SPF record and add `include:spf.brevo.com` before `~all`; never add a second `v=spf1` record. The record stays far
below SPF's limit of 10 DNS lookups.

Verify: `dig +short TXT <domain>` shows exactly one line starting with `"v=spf1`.

## 3. DMARC: start with monitoring, tighten later

1. Start: `_dmarc` TXT `v=DMARC1; p=none; rua=mailto:rua@dmarc.brevo.com` (Brevo's suggested value; reports go to Brevo's
   DMARC dashboard). To receive the reports yourself instead, use `rua=mailto:dmarc@<domain>` and add a routing rule
   `dmarc@` → `<owner inbox>` in step 4 (expect a few XML reports a day).
2. After 2–4 weeks with every legitimate source passing (Brevo DMARC report, or headers as in step 6): change `p=none`
   to `p=quarantine; pct=100`, later `p=reject` if nothing breaks.
3. Keep exactly one `_dmarc` record. Gmail and Yahoo require a DMARC record for bulk senders; `p=none` satisfies that.

## 4. Cloudflare Email Routing: `support@<domain>` → the owner's inbox (owner: Cloudflare dashboard)

1. Cloudflare → `<domain>` → **Email → Email Routing → Get started / Onboard domain**. Cloudflare lists the records it adds
   and adds them itself:
   - MX `@` → `route1.mx.cloudflare.net`, `route2.mx.cloudflare.net`, `route3.mx.cloudflare.net` (priorities set by Cloudflare);
   - TXT `@` → `v=spf1 include:_spf.mx.cloudflare.net ~all` (**merge with Brevo as in step 2: one SPF record**);
   - TXT `cf2024-1._domainkey` → Cloudflare's DKIM key for forwarded mail.
   Remove any other MX records for `<domain>` first (a new domain has none).
2. **Destination addresses → Add** `<owner inbox>` → open Cloudflare's verification email → "Verify email address".
3. **Routing rules → Create address**: `support` → action "Send to an email" → `<owner inbox>` → Save. Optional: `noreply`
   → "Drop" (people do reply to `noreply@`), and `dmarc` → `<owner inbox>` if step 3 uses it.
4. Do not turn on "Catch-all" (it invites spam to every made-up address).

Verify: from another account, send a mail to `support@<domain>`; it arrives in `<owner inbox>`. Email Routing → Activity
log shows "Forwarded".
Rollback: Email Routing → Disable (Cloudflare removes its MX records; put back the SPF record of step 2 without
`include:_spf.mx.cloudflare.net`).

Replying *as* `support@<domain>` is not part of Email Routing (it only receives). If the owner wants that later: Gmail →
Settings → Accounts → "Send mail as" through Brevo's SMTP relay (`smtp-relay.brevo.com`, port 587, Brevo SMTP key);
it is covered by the same DKIM.

## 5. Render: switch the sender (agent or owner; Render dashboard)

Only after step 1 is green in Brevo.

1. Render → backend service → **Environment**:
   - `EMAIL_PROVIDER` = `brevo` (keep it explicit);
   - `EMAIL_FROM` = `noreply@<domain>` (replaces the personal address);
   - `EMAIL_FROM_NAME`: remove it, or set it to `Platform`, so auth emails carry the per-language platform name. Set a
     fixed value only if the owner wants the same name in all three languages. If the platform name changed, also
     change `APP_NAME` in `email_service.py` and `common.appName` in the three dictionaries (one commit).
   - remove `SMTP_FROM_EMAIL`, `SMTP_SERVER`, `SMTP_USER`, `SMTP_PASSWORD` if present (Render free blocks SMTP; they only
     confuse the fallback). Keep `BREVO_API_KEY`. Remove `RESEND_API_KEY` unless Resend is the chosen provider.
2. Save → Render redeploys (no code change). Wait for `/health` to answer.
3. Write down the old values somewhere private (not in the repo) for the rollback.

## 6. Verify

1. Admin → Services: the email card shows Brevo connected; `GET /api/v1/platform/health` (as admin) shows email `ok`.
2. Register a new test account with an address you can read (a Gmail test address) or use "Забыли пароль?" for an
   existing test account. The code arrives within a minute, From `<platform name> <noreply@<domain>>`.
3. In Gmail: the message → ⋮ → **Show original**. Expect `DKIM: 'PASS' with domain <domain>`, `SPF: 'PASS'` (for Brevo's
   bounce domain on shared IPs; that is normal) and `DMARC: 'PASS'`. In the raw headers: `Authentication-Results: ...
   dkim=pass header.i=@<domain> ... spf=pass ... dmarc=pass (p=NONE ...) header.from=<domain>`.
4. Optional score: send the code email to the address that mail-tester.com shows and aim for 9/10 or more.
5. Brevo → Transactional → Logs shows the message as delivered.

## 7. Rollback

- Sending broken after step 5 (Brevo rejects `noreply@<domain>`, codes do not arrive): Render → set `EMAIL_FROM` back to
  the previous value (the personal address, still a verified Brevo sender) and save. Nothing in the database depends on
  the sender. Fix the domain in Brevo, then repeat step 5.
- DMARC stricter than it should be (mail lands in spam or is rejected after `p=quarantine`): set `_dmarc` back to `p=none`.
- Forwarding broken: Email Routing → Disable (step 4 rollback); sending is unaffected.
- Never delete the old verified sender in Brevo until the new domain has worked for a week.

## Support address in the product

As of 2026-11-13 the product shows **no** contact or support address: `/[lang]/contacts` says "contact details will appear
here soon" (`contacts.body` in the dictionaries), and the privacy and policy pages, the footer and the emails name no
address (emails say "contact the platform administrator"). When `support@<domain>` exists, add it in **one** place: a
public frontend env variable `NEXT_PUBLIC_SUPPORT_EMAIL` (Vercel, read by one helper and shown on the contacts page and
the footer), with the visible wording in `en.json`, `ky.json`, `ru.json`. No address in code or dictionaries.

## Sources (checked 2026-11-13)

- Brevo, authenticate your domain (Brevo code, DKIM, DMARC):
  https://help.brevo.com/hc/en-us/articles/12163873383186-Authenticate-your-domain-with-Brevo-Brevo-code-DKIM-DMARC
- Brevo API, domain authentication records: https://developers.brevo.com/docs/domain-authentication-and-verification
- Brevo, DMARC policy FAQ (single record with `rua`):
  https://help.brevo.com/hc/en-us/articles/10415456027666-FAQs-What-is-a-DMARC-policy-and-how-does-it-affect-the-sending-of-my-emails
- Brevo, Gmail/Yahoo/Microsoft sender requirements:
  https://help.brevo.com/hc/en-us/articles/14925263522578-Comply-with-Gmail-Yahoo-and-Microsoft-s-requirements-for-email-senders
- Cloudflare Email Routing, enable and routing rules: https://developers.cloudflare.com/email-routing/get-started/enable-email-routing/
- Cloudflare Email Routing DNS records (MX, SPF merge, DKIM): https://developers.cloudflare.com/email-routing/setup/email-routing-dns-records/
- Cloudflare Email Routing postmaster (SPF include): https://developers.cloudflare.com/email-routing/postmaster/
