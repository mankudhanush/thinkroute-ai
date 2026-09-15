# ThinkRoute AI backend

The FastAPI service provides provider management, manual model selection, direct chat, automatic routing, repository context, and SQLite conversation history.

## Run

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`; interactive documentation is at `/docs`.

Set `ENCRYPTION_KEY` to a Fernet key in production. If omitted in development, the API derives one from `SECRET_KEY`. API keys are never returned by the API.

Supported providers are `openrouter`, `ollama`, `groq`, `nvidia`, `cloudflare`, and Gemini where configured by the provider layer.

## Configuration

Copy `.env.example` to `.env` and set provider credentials only for the providers you intend to use. Never commit `.env`, API keys, account IDs, or the generated `data/` directory.

`ENCRYPTION_KEY` should be a Fernet key in production. When it is empty in development, the service derives a key from `SECRET_KEY`.

## API areas

- `GET /providers` and provider connection/model refresh endpoints
- `POST /chat` for a selected provider and model
- `POST /chat/auto` for automatic intent-based routing
- `GET /chat/history/{conversation_id}` for persisted conversation history
- `GET /docs` for the generated OpenAPI documentation

