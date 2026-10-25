# AURA — Personal Wellness

AURA is a local-first personal wellness tracker for nutrition, workouts, measurements, habits, skincare routines, water, and sleep. The React interface talks to a FastAPI API backed by a persistent SQLite database. Authentication uses Argon2 password hashes and server-side, HttpOnly session cookies.

## Prerequisites

- Python 3.10 or newer (tested here with Python 3.14)
- Node.js 20 or newer and npm

No Docker, hosted service, external API, or email account is required. Google Fonts are not required; the app uses system fonts. Once dependencies are installed, the application works offline.

## Install

Run these commands from the AURA project directory in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm.cmd install
Set-Location ..
```

If PowerShell blocks activation, use `.venv\Scripts\python.exe -m pip install -r backend\requirements.txt` and `.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000` without activating the environment.

## Configure and initialize

The API creates the SQLite schema and a small estimated Indian-food catalogue on first startup. By default, the database is stored at `backend\data\aura.db`. The database directory is local and excluded from Git.

Optional configuration is listed in `.env.example`. Environment variables are read by the backend process; `.env` files are not automatically loaded. Set a different database directory before starting the API if needed:

```powershell
$env:AURA_DATA_DIR = "C:\path\to\private\aura-data"
$env:AURA_FRONTEND_ORIGIN = "http://127.0.0.1:5173"
$env:AURA_COOKIE_SECURE = "false"
```

Keep `AURA_COOKIE_SECURE=false` only for local HTTP development. For HTTPS deployment, set it to `true` and configure a production frontend origin and HTTPS reverse proxy. The development server binds to loopback only.

## Run locally

Open two PowerShell terminals, each starting in the AURA project directory.

Terminal 1 — backend:

```powershell
.\.venv\Scripts\Activate.ps1
Set-Location backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Terminal 2 — frontend:

```powershell
Set-Location frontend
npm.cmd run dev
```

Open <http://127.0.0.1:5173>. Create an account to begin; the first visit includes onboarding. The API's OpenAPI documentation is at <http://127.0.0.1:8000/docs>, and its health endpoint is <http://127.0.0.1:8000/api/health>.

## Tests and build

```powershell
Set-Location backend
python -m pytest -q
Set-Location ..\frontend
npm.cmd run build
```

## Implemented functionality

- Registration, sign-in/out, Argon2 password hashing, HttpOnly sessions, same-site cookies, CSRF checks on authenticated writes, and per-user data ownership.
- Onboarding, personal goals, editable nutrition and water targets, and an optional calorie/macronutrient estimate using Mifflin–St Jeor for adults with suitable profile inputs. Users can review and explicitly apply a recalculation; manually selected targets are not silently replaced.
- Local search across estimated Indian foods, nutrition entry creation/edit/deletion through the API, daily calories/macronutrients, and a persistent journal.
- Deterministic natural-language food parsing for supported local catalogue items, with clarification for unknown or ambiguous descriptions. Parsed meals show estimated values and assumptions and require confirmation before saving; submissions are idempotent.
- Configurable meal reminders for breakfast, snacks, lunch, dinner, and custom categories, including IANA time zone, quiet hours, snooze, skip/dismiss/completion state, and optional browser notifications. Reminder delivery is deduplicated per meal and local day.
- A lightweight local assistant for meal parsing, water, weight, sleep, completed-workout logging, and daily calorie/protein summaries. It uses deterministic commands and does not require a paid AI service.
- Workout plan creation, active sessions, set logging, finishing workouts, and recent-session history.
- Weight/body-measurement history and data-backed trend charts.
- Habit creation and daily completion tracking; configurable skincare routines and completion history.
- Water logging, history, edit/delete, and sleep logging, including sleep sessions crossing midnight.
- Selectable completed-week reports for logged nutrition averages, workouts, weight, sleep, habits, and water. Missing logs are shown as missing rather than treated as zero.
- CSV export of recorded body measurements and matching daily nutrition summaries.
- Responsive dark-first navigation and dashboard, including honest empty states.

## Known limitations

- Nutrition and calorie values are estimates, not medical advice or measured metabolism. Initial estimates use Mifflin–St Jeor with approximate activity factors (1.20, 1.375, 1.55, 1.725, 1.90), configurable modest goal adjustments (+200 kcal surplus or −300 kcal deficit by default), protein assumptions (1.4 or 1.8 g/kg), and fat at about 25% of target energy; carbohydrates fill the remainder using 4/4/9 kcal-per-gram conversions. Rounding, fiber, and food-database variation mean macros may not exactly match calorie values. Estimates are skipped for minors, adults over 80, incomplete inputs, unsupported sex selections, low unsafe targets, or when the user opts out. Targets are never automatically changed in response to weight changes.
- Meal and browser reminders are checked every 30 seconds only while the site is open and the API is reachable. Browser notifications require browser permission. There is no background or operating-system scheduler; reminders cannot be relied on while the browser is closed or the computer is sleeping, switched off, or offline. IANA time zones and daylight-saving transitions are used for scheduled reminder checks.
- Food parsing recognizes only a small, explicit vocabulary from the local catalogue and supported serving units; unsupported descriptions require manual logging. Values in the seeded catalogue are estimates.
- Adaptive multi-week weight-rate coaching, automated workout scheduling/progression and personal-record analytics, hydration reminders, ingredient/allergy/budget-aware meal suggestions, achievements/gamification, and a broad exercise catalogue are not implemented. Existing weight charts, workout history, hydration records, and weekly reports remain available.
- Full routines/wardrobe management, avatar customization, private progress-photo uploads, saved meals/recipes, and account password-reset email delivery are not implemented yet. Password recovery requires a future local account-administration workflow or an email service.
- Values are stored and displayed in metric units (kg/cm/ml). Imperial display and conversion are deferred; only metric measurements are available in this version.
- CSV export currently includes body measurement dates and nutrition totals for those dates; it is not a complete archive of every module.
- Nutrition and other daily logs use the local browser date and local API machine time. For consistent daily boundaries, keep the browser and API on the same device/time zone; the reminder time zone is configurable independently.
- SQLite and uploaded data (none are enabled yet) are stored locally. Anyone with access to your Windows account or database backups can access those files. Protect the device and store backups securely. Account deletion is permanent.
- The app is intended for a trusted, single-device local environment. Review deployment, HTTPS, secrets, backups, migrations, and operational security before exposing it to other devices or the public internet.

## Data backup and reset

Stop the backend before copying the database. Back up `backend\data\aura.db` to a private location; database backups contain account hashes and personal wellness records.

To reset all local records, stop the backend and remove only `backend\data\aura.db`. Restarting the API recreates a clean database and the estimated food catalogue. This is destructive and cannot be undone.

There is no seeded demo account; create your own account in the app. Uploaded photos are not implemented and no user photo directory is created.

## Test the upgrade

1. Sign in or create an account and complete the profile. For a calorie estimate, enter an adult birth date, height, current weight, activity level, and optionally select male or female for the equation. Other or missing sex selections intentionally leave the estimate unavailable.
2. Open **Settings → Calorie & macro estimate**. Review BMR, estimated maintenance, goal calories, and macro assumptions. **Review & apply these targets** is the explicit confirmation; editing profile details alone does not replace targets.
3. In **Settings → Meal reminders**, configure the time zone and a meal time a minute or two ahead, then save. Keep AURA open. The reminder should appear in the app; choose **Not yet** to snooze or **Yes, I've eaten** to open the assistant.
4. In the daily assistant, enter `I ate 2 bananas and 250 ml milk`. Review the estimated catalogue values and assumptions, choose the meal category, then confirm to save. Repeated confirmation of the same request does not create duplicate entries.
5. Test a supported water command such as `I drank 500 ml water`, then check the dashboard. Open **Analytics** to browse saved reports for completed weeks.

The estimate follows `BMR = 10 × kg + 6.25 × cm − 5 × age + sex constant`, where the constant is `+5` for male and `−161` for female. Maintenance is `BMR × activity factor`; the selected goal adds or subtracts its configured adjustment. Protein and fat use the documented assumptions above, and carbohydrate grams fill remaining target calories.

No additional scheduler setup is required or provided. For local development, start the backend and frontend using the commands in **Run locally**; both must remain available for meal reminders.
