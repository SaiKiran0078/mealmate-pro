# 🥘 MealMate Pro

> **Cook what you already have.** Plan daily or weekly meals around pantry ingredients, prioritize food nearing expiry, review nutrition, and build a shopping list for what is missing.

![Python](https://img.shields.io/badge/Python-3.12%2B-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688)
![SQLite](https://img.shields.io/badge/Database-SQLite-003B57)
![Auth](https://img.shields.io/badge/Auth-JWT-6C5CE7)
![License](https://img.shields.io/badge/License-MIT-green)

MealMate Pro is a full-stack meal-planning web application built with FastAPI, SQLite, JWT authentication, and a responsive HTML/CSS/JavaScript interface.

## ✨ Features

- **Pantry management:** Track ingredients in separate batches, quantities, units, and expiry dates.
- **Recipe discovery:** Search the built-in recipe catalog and optionally discover recipes online.
- **Daily and weekly planning:** Generate plans for selected meal types, servings, diet preferences, and calorie targets.
- **Expiry-aware suggestions:** Prioritize ingredients that should be used soon.
- **Nutrition summaries:** Display calories and macronutrients where recipe data is available.
- **Shopping lists:** Identify ingredients missing from the planned meals.
- **Cooking workflow:** View recipe instructions, swap meals, and mark meals as cooked.
- **Fitness and nutrition tools:** Track goals and workout/food information supported by the application.
- **Accounts and data isolation:** JWT-based authentication and per-user data separation.
- **Responsive interface:** Meal cards with recipe visuals, meal labels, cooking time, calories, and protein.

## 🖼️ Screenshots

Add screenshots from your running application to `docs/screenshots/` and update the paths below when ready.

```text
docs/
└── screenshots/
    ├── overview.png
    ├── pantry.png
    ├── recipes.png
    └── meal-planner.png
```

<!-- Replace these placeholders with real screenshots once committed. -->
<!-- ![Meal planner](docs/screenshots/meal-planner.png) -->

## 🧰 Tech stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Authentication | JWT, PBKDF2 password hashing |
| Database | SQLite |
| Frontend | HTML, CSS, JavaScript |
| Tests and quality | pytest, Node.js tests, Ruff |
| Deployment | Docker, Docker Compose; Render/Railway with persistent storage |

## 📁 Project structure

```text
mealmate-pro/
├── app/
│   ├── core/              # Planning, matching, nutrition, units and stock logic
│   ├── repositories/      # Database queries
│   ├── routers/           # Authentication and application API routes
│   ├── static/            # Browser UI, styles and JavaScript
│   ├── seed/              # Built-in recipe and ingredient data
│   ├── main.py
│   ├── db.py
│   └── security.py
├── tests/                 # Python and JavaScript tests
├── docs/                  # API, architecture, audit and build documentation
├── Dockerfile
├── docker-compose.yml
├── render.yaml            # Render Blueprint configuration
├── requirements.txt
├── requirements-dev.txt
├── .env.example
└── README.md
```

## 🚀 Run locally (Windows PowerShell)

### 1. Requirements

- Python 3.12 recommended
- Git
- Node.js only if you want to run the JavaScript tests

### 2. Clone the repository

After you push this project to GitHub, use your repository URL:

```powershell
git clone https://github.com/YOUR-USERNAME/mealmate-pro.git
cd mealmate-pro
```

If you already downloaded or extracted the project, open that folder in VS Code and skip cloning.

### 3. Create and activate a virtual environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

If PowerShell blocks activation, run this for the current terminal only:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 4. Configure environment variables

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_hex(32))"
notepad .env
```

Copy the generated secret into the `JWT_SECRET=` line. Keep the secret stable between restarts and never commit `.env`.

### 5. Start the application

```powershell
python -m uvicorn app.main:create_app --factory --reload --env-file .env
```

Open **http://127.0.0.1:8000**. Interactive API documentation is available at **http://127.0.0.1:8000/docs**.

Stop the server with `Ctrl+C`.

## 🧪 Run checks

From the project root with the virtual environment activated:

```powershell
python -m pytest
node --test tests/js/*.test.js
ruff check .
```

Run the checks supported by your local environment. If a command fails, review its output before deploying.

## 🐳 Run with Docker

Create a local `.env` file and set `JWT_SECRET` to a randomly generated secret. Then run:

```powershell
docker compose up --build
```

The container uses `/data/mealmate.db` for its SQLite database. For persistent deployments, mount a durable volume at `/data`.

## ☁️ Deploy online

### Recommended: Render with persistent disk

This repository includes a `render.yaml` Blueprint configuration. To deploy:

1. Push the project to a **new or existing GitHub repository**.
2. Sign in to Render and choose **New → Blueprint**.
3. Connect the repository and select `render.yaml`.
4. Review the service configuration and deploy.
5. Confirm that the service has a persistent disk mounted at `/data`.
6. In the Render dashboard, confirm `JWT_SECRET` is generated as a secret environment variable.
7. Wait for the deploy to finish and open the generated `onrender.com` URL.

**Persistence and cost:** SQLite needs durable storage in a hosted environment. Render persistent disks may require a paid service plan; check the current plan and pricing before deploying. Do not remove the disk or change `MEALMATE_DB` after users have created data, or the service may appear to start with an empty database.

### Deployment checklist

- [ ] `JWT_SECRET` is set to a strong, private value.
- [ ] SQLite database path is `/data/mealmate.db`.
- [ ] Persistent storage is mounted at `/data`.
- [ ] `/health` health check passes.
- [ ] Register, log in, and verify that pantry and saved plans persist after a redeploy.
- [ ] Test the live site on desktop and mobile.
- [ ] Keep `.env`, database files, and real user data out of GitHub.

## 🔐 Security and data notes

- Never commit `.env`, JWT secrets, access tokens, or a live database containing user data.
- `.gitignore` excludes `.env` and SQLite database files.
- Keep `JWT_SECRET` stable between deployments; changing it invalidates existing tokens.
- Back up persistent data before database/schema changes.
- Food photos may be loaded from external image providers and therefore require an internet connection.

## 📚 Documentation

- [API reference](docs/API.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Build guide](docs/BUILD_GUIDE.md)
- [Feature overview](docs/FEATURES.md)
- [Project audit](docs/AUDIT.md)

## 🛣️ Future improvements

- PostgreSQL support and managed database migrations
- Expanded recipe and verified nutrition coverage
- Automated UI/browser regression tests
- Additional meal-plan personalization and recipe-image matching

## 📄 License

MIT — see [LICENSE](LICENSE).
