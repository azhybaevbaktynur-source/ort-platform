# Incident
**First 5 minutes**
1. Is `/health` up? (`https://ort-platform-w77q.onrender.com/health`, allow 90 s for a cold start.) Is `/ru/login` up?
2. Open the GitHub issue "Uptime: site check failed" if the schedule raised one.
3. Render logs: JSON lines. 5xx and requests over 1 s are always logged; find `request_id` and `route`. Logs hold no email, IP, query string or answers.
4. Recent deploy? If yes and it matches the start time, roll back (`ROLLBACK.md`) first, investigate later.

**During an exam**
- Open attempts are never stopped by the privacy gate; autosave and submit stay allowed.
- If the server is slow, do not restart it while students are saving unless it is down: acknowledged answers are in the database, a restart drops only in-flight requests.
- Tell the teacher in plain words: what is affected, since when, what to do (wait or reload).

**After**
- Write 5 lines: what happened, when, impact, cause, fix. Add to `docs/PRODUCT_DECISIONS.md` if a rule changes.
- If personal data may have leaked: tell the owner at once; the legal duty to notify is a legal question (see `LAUNCH_CHECKLIST.md`).
- Rotating `SECRET_KEY` logs everyone out; use `SECRET_KEY_PREVIOUS` to roll without logging out.
- Two-step login (S1) keys come from `SECRET_KEY` too. Keep `SECRET_KEY_PREVIOUS` until every platform admin has signed in once with a code (that re-encrypts their secret with the new key), then each admin makes new recovery codes on `/admin/security`: old recovery codes stop working when the previous key is removed. An admin who lost their phone and recovery codes: `python make_admin.py --reset-2fa <email>` (ends their sessions; they set it up again on the next admin visit). A stolen admin session: another admin uses "End sessions" on the user page, or the admin uses "End all my sessions".
