# ThinkRoute AI

ThinkRoute AI is a repository-aware, multi-provider AI workspace. It combines a Next.js interface with a FastAPI service that manages providers, selects models, routes prompts by intent, stores conversation history, and supplies repository context to code-focused chats.

## What it does

- Connects supported hosted providers and local Ollama models.
- Supports manual model selection and automatic routing by prompt intent and complexity.
- Persists conversations in a local SQLite database during development.
- Indexes, retrieves, and sends repository context to RAG chat workflows.
- Exposes inference and provider state through a focused web workspace.

## Architecture

The application runs as two local services:

```text
Browser (Next.js :3000)
	|
	| HTTP / JSON
	v
FastAPI (:8000) ---- Provider adapters ---- Hosted providers / Ollama
	|
	+---- SQLite conversation and provider state
	+---- Repository indexing, retrieval, RAG, and editing services
```

The frontend lives in `app/`, `components/`, `hooks/`, `lib/`, `services/`, `stores/`, and `types/`. The backend and provider adapters live in `backend/app/`. Design proposals and context-engine notes are in `docs/`.

## Requirements

- Node.js 20 or newer and npm
- Python 3.11 or newer
- Credentials for any hosted provider you intend to connect
- Optional: Ollama running locally for local inference and classification

## Local setup

### Frontend

From the repository root:

```powershell
npm install
Copy-Item .env.example .env.local
npm run dev
```

The frontend opens at `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL` in `.env.local` when the API is not at `http://127.0.0.1:8000`.

### Backend

In a second terminal:

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. Health status is exposed at `/health`, and interactive OpenAPI documentation is available at `/docs`.

## Configuration

The frontend only needs `NEXT_PUBLIC_API_URL`:

| Variable | Purpose | Example |
| --- | --- | --- |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL | `http://127.0.0.1:8000` |

Backend settings are documented in [`backend/.env.example`](backend/.env.example):

| Variable | Purpose |
| --- | --- |
| `APP_NAME`, `APP_ENV` | Service name and environment |
| `DATABASE_PATH` | SQLite database location |
| `SECRET_KEY` | Application secret; replace the development value |
| `ENCRYPTION_KEY` | Fernet key used to encrypt stored provider credentials |
| `PROVIDER_TIMEOUT_SECONDS` | Upstream provider request timeout |
| `CORS_ORIGINS` | Comma-separated allowed frontend origins |
| `OLLAMA_BASE_URL` | Ollama server URL |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare provider account identifier |

Provider credentials are entered through the provider workflow or configured according to the provider adapter. Never commit credentials, `.env` files, the SQLite database, or generated repository data.

## API surface

| Area | Endpoints |
| --- | --- |
| System | `GET /health` |
| Providers | `GET /providers`, `POST /providers/connect`, `DELETE /providers/{provider}`, `POST /providers/{provider}/refresh_models` |
| Chat | `POST /chat`, `POST /chat/auto`, `GET /chat/history/{conversation_id}` |
| Models | Model discovery and selection routes are grouped under `/models` |
| Repository intelligence | Repository context, chunking, indexing, retrieval, RAG, and editing routes are grouped under their respective routers |

The complete request and response schemas are generated at `http://127.0.0.1:8000/docs` while the backend is running.

## Development commands

```powershell
# Frontend
npm run dev
npm run typecheck
npm run build

# Backend, from the backend directory with .venv active
python -m pytest
```

The Python test command runs the available backend and integration tests. Install any test-only dependencies required by the tests in the active virtual environment.

## Security and data handling

- Keep `backend/.env` and `.env.local` local; both are ignored by Git.
- Use a strong, unique `SECRET_KEY` and an explicit Fernet `ENCRYPTION_KEY` outside development.
- Keep `CORS_ORIGINS` limited to trusted frontend origins.
- Provider API keys are handled by the backend and are not returned in provider responses.
- Review repository context and editing permissions before connecting an untrusted workspace.
- `backend/data/`, build output, virtual environments, caches, and local tooling are ignored by Git.

## Project documentation


## Publish to GitHub

The project is ready for its first remote push. After installing the [GitHub CLI](https://cli.github.com/) and signing in with `gh auth login`, run these commands from the repository root:

```powershell
gh repo create thinkroute-ai --private --source=. --remote=origin --push
```

Use `--public` instead of `--private` only when the source code and provider integration details are ready for public distribution. If the repository already exists, configure the remote and push the existing commit instead:

```powershell
git remote add origin https://github.com/<your-account>/thinkroute-ai.git
git push -u origin master
```
## License

No license has been selected yet. Add a license before accepting external contributions or redistributing the project.