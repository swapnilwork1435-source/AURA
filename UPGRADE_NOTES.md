# AURA Automation Upgrade Notes

## Included changes
- Added `/api/automations/settings`, `/api/automations/overview`, `/api/automations/run-now`, and per-user event acknowledgement routes.
- Added persistent automation preferences, event inbox, and achievement tables; existing database records are preserved and new tables are created by the normal startup migration path.
- Added scheduled hydration events, morning briefings, evening check-ins, conservative logged-data suggestions, and persistent achievements.
- Added higher-load personal-record event detection to workout set logging.
- Added a React Automation center page with settings, summaries, suggestions, achievements, and an event inbox.
- Added `backend/app/automation_worker.py` for one-minute scheduled checks while the machine is awake.
- Added `backend/backup_database.py` for consistent SQLite backups, integrity checks, and safe restore with a pre-restore backup.
- Fixed meal reminder initialization so deleted custom reminders are not silently recreated on every read.
- Added regression tests for automation settings, idempotency, user isolation, personal records, achievements, and hydration reminders.

## Run
1. Follow the existing README setup steps and install dependencies.
2. Run the backend and frontend as usual.
3. To enable scheduled checks while the browser is closed, open a third terminal:
   `cd backend`
   `python -m app.automation_worker`
4. Open the **Automation** page to configure the schedule or run a check manually.
5. Back up SQLite with `cd backend` then `python backup_database.py`.

## Validation
- Backend tests: `python -m pytest -q` — 21 passed.
- TypeScript project check: `node node_modules/typescript/bin/tsc -b` passed against the supplied dependency tree.
- Vite bundling was not completed in this Linux validation environment because the uploaded Windows `node_modules` archive lacks the Linux-specific optional Rollup binary. Reinstall frontend dependencies on the target OS (`npm install` / `npm.cmd install`) before building.

## Boundaries
- Automations persist events; they do not yet deliver native OS/Web Push notifications while the browser is closed.
- Worker jobs require the backend database, worker process, and awake computer.
- Suggestions are rule-based and use logged data only. No calorie target is silently changed.
- The archive intentionally excludes the local SQLite database, node_modules, build output, and caches. Existing local data is not included in or replaced by this source package.
