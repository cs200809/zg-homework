# Repository Guidelines

## Agent Communication

与用户交互时使用中文。

## Project Structure & Module Organization

- `zg-homework-server/` contains the FastAPI backend. Application code is in `app/`, organized into routers, schemas, services, models, and database modules; tests are in `tests/`.
- `zg-homework-web/` contains the React, TypeScript, Vite, and Ant Design frontend. Place pages, reusable components, API clients, and state in the corresponding `src/` directories.
- `zg-homework-docs/` holds the PRD, configuration guidance, SQL, and supporting assets. `docs/` contains additional project documentation. `zg-homework-tests/` contains tests for packaging and deployment scripts.
- Treat `zg-homework-docs/sys_doc/PRD.md` as the requirements and API contract reference.

## Build, Test, and Development Commands

Use Python 3.12, Node.js 20 or later, and MySQL 8. From the repository root:

- `python3.12 -m venv .venv` and `.venv/bin/pip install -r zg-homework-server/requirements.txt` set up backend dependencies.
- `cd zg-homework-server && ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000` starts the API.
- `npm --prefix zg-homework-web ci` installs frontend dependencies; `npm --prefix zg-homework-web run dev` starts Vite.
- `npm --prefix zg-homework-web run build` type-checks and builds the frontend.

The root README contains historical Makefile commands; the root Makefile and related operational scripts have been removed.

## Coding Style & Naming Conventions

Follow the surrounding code: four-space indentation and `snake_case` for Python; TypeScript/React components use `PascalCase` and variables use `camelCase`. Keep API and business logic in their existing modules. The frontend defines an `npm run lint` ESLint script; check its configuration before relying on it.

## Testing Guidelines

Backend tests use pytest and `test_*.py` filenames. Configure `DATABASE_URL` to a dedicated isolated MySQL database before running `cd zg-homework-server && ../.venv/bin/pytest`; tests can commit or delete data. Add focused tests for behavior changes and reuse fixtures in `tests/conftest.py`. There is no documented coverage threshold.

## Commit & Pull Request Guidelines

Recent commits commonly use concise conventional prefixes, optionally scoped, such as `docs(deploy): ...`; descriptions may be in Chinese. Describe the change and its motivation in pull requests, link relevant issues, and report tests run. Include screenshots for visible UI changes and note database or configuration changes.

## Configuration

Copy `zg-homework-server/.env.example` to `.env` for local settings, and set a private `JWT_SECRET` and the intended database URL. Do not commit credentials or real user data.
