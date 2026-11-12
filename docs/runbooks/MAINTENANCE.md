# Daily database maintenance
Design: `docs/phases/DB_STORAGE_REVIEW.md` §5 and the D2 note; owner rules in `docs/PRODUCT_DECISIONS.md`
("Owner 2026-11-12: storage retention answers"). Code: `backend/app/lms/maintenance/`.

**What runs** (in this order, each bounded and in its own transaction; a failed task is listed in `errors`, the others still run):
1. existing purges: expired attempts finalized, application answers, teacher applicants' phones, buyer names on old codes;
2. expired password-reset tokens and email codes nulled;
3. unused guardian pairing codes and email changes expired more than 7 days ago, expired rate-limit buckets;
4. never-verified accounts older than 90 days with nothing attached but their sign-up consent;
5. staff preview attempts (not in progress, or in progress for more than 24 h);
6. test-student (Student view) attempts by the same rule; files of removed test students; removed test students with their rows;
7. the database size for the Services panel.
Never deleted: students' attempts, answers, grades and grade events, the audit log, consent records, data requests,
enrollment events of real students, assessment and question versions, tombstones, teacher requests.

**Secrets (names only).** One token in two places, the same value:
- Render, backend service env: `ATTEMPT_SWEEP_TOKEN` (also opens `/internal/attempts/sweep` and `/internal/purge-applications`);
- GitHub, repository secret: `SWEEP_TOKEN`.
Make it with `python3 -c "import secrets; print(secrets.token_urlsafe(32))"`, paste it into both, never into chat, commits
or logs. While `SWEEP_TOKEN` is unset the workflow skips with a notice; while `ATTEMPT_SWEEP_TOKEN` is unset the route
answers 404 and the workflow opens the issue "Maintenance: daily cleanup failed".

**Schedule.** `.github/workflows/maintenance.yml`, daily at 04:30 UTC, applies (`dry_run=0`), two tries (the first may
wake Render). A failure opens or updates one issue; the next success closes it. GitHub may delay or skip a run; then
the admin overview starts the safe tasks 1-3 at most once per 12 hours (production only).

**Run it by hand.**
- Admin: Admin panel, Сервисы, block "Очистка базы": "Проверить (без удаления)" is a dry run, "Очистить" applies after a
  confirmation. Both are audited as `maintenance.run`; the last run and its counts stay on the page.
- GitHub: Actions, Maintenance, "Run workflow".
- Shell (counts only in the answer; `dry_run=1` only counts):
  ```bash
  curl -fsS --max-time 120 -X POST -H "X-Sweep-Token: $SWEEP_TOKEN" \
    "https://ort-platform-w77q.onrender.com/api/v1/internal/maintenance?dry_run=1"
  ```

**Check it worked.** The Services block shows "Последний запуск" with `по расписанию` and today's time; the JSON log has
one `maintenance task` line per task with counts only.
