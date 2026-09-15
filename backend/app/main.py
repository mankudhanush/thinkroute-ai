import logging
import sys

# Windows consoles default to cp1252, which can't encode log glyphs like → or ✓.
# Force UTF-8 so structured log lines never raise UnicodeEncodeError.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.chat import router as chat_router
from app.api.models import router as models_router
from app.api.providers import router as providers_router
from app.services.repository import router as repository_router
from app.services.repository.chunk_router import router as repository_chunk_router
from app.services.repository.index_router import router as repository_index_router
from app.services.repository.retrieval_router import router as repository_retrieval_router
from app.services.repository.rag_router import router as repository_rag_router
from app.services.repository.editing_router import router as repository_editing_router
from app.config import settings
from app.database.database import Database
from app.errors import AppError
from app.models.schemas import HealthResponse
from app.services.chat_service import ChatService
from app.services.model_service import ModelService
from app.services.provider_service import ProviderService
from app.services.storage_service import StorageService
from app.services.auto_router import AutoRouter
from app.services.hybrid_classifier import HybridClassifier
from app.services.intent_classifier import IntentClassifier
from app.services.rule_classifier import RuleClassifier
from app.services.routing_engine import RoutingEngine
from app.services.model_selector import ModelSelector
from app.services.memory.memory_engine import MemoryEngine

# ---------------------------------------------------------------------------
# Logging – visible in the uvicorn console
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG if settings.environment == "development" else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
# Silence noisy third-party loggers
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application bootstrap
# ---------------------------------------------------------------------------
database = Database(settings.database_path)
storage_service = StorageService(database)
provider_service = ProviderService(storage_service)
model_service = ModelService(storage_service, provider_service)

# Context-Aware Memory Engine — provider-independent, shared by both modes.
memory_engine = MemoryEngine()

chat_service = ChatService(storage_service, provider_service, model_service, memory_engine)

# Auto Mode services — hybrid classifier (rules first, qwen3:4b only when uncertain)
rule_classifier = RuleClassifier()
intent_classifier = IntentClassifier(api_base=settings.ollama_base_url)
hybrid_classifier = HybridClassifier(rule_classifier, intent_classifier)
routing_engine = RoutingEngine()
model_selector_service = ModelSelector(storage_service)
auto_router = AutoRouter(storage_service, provider_service, hybrid_classifier, routing_engine, model_selector_service, memory_engine)

app = FastAPI(title=settings.app_name, version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    logger.warning("AppError %d [%s]: %s", exc.status_code, exc.code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code, "detail": exc.detail})


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    return HealthResponse(status="ok", service=settings.app_name)


app.include_router(providers_router)
app.include_router(models_router)
app.include_router(chat_router)
# Repository Intelligence Engine (Phase 1) — independent, additive module.
app.include_router(repository_router)
# Repository Intelligence Engine (Phase 2) — Intelligent Chunk Generator.
app.include_router(repository_chunk_router)
# Repository Intelligence Engine (Phase 3) — Repository Indexing Engine.
app.include_router(repository_index_router)
# Repository Intelligence Engine (Phase 4) — Repository Retriever.
app.include_router(repository_retrieval_router)
# Repository Intelligence Engine (Phase 5) — RAG chat (context/prompt/chat).
app.include_router(repository_rag_router)
# Repository Intelligence Engine (Phase 5) — AI editing (edit/apply/diff).
app.include_router(repository_editing_router)

logger.info("ThinkRoute API started (env=%s)", settings.environment)
