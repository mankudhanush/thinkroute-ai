from fastapi import APIRouter, Depends

from app.models.schemas import AutoChatRequest, AutoChatResponse, ChatRequest, ChatResponse, HistoryMessage
from app.services.chat_service import ChatService
from app.services.auto_router import AutoRouter

router = APIRouter(prefix="/chat", tags=["chat"])


def get_chat_service() -> ChatService:
    from app.main import chat_service
    return chat_service


def get_auto_router() -> AutoRouter:
    from app.main import auto_router
    return auto_router


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest, service: ChatService = Depends(get_chat_service)) -> ChatResponse:
    return await service.chat(request)


@router.get("/history/{conversation_id}", response_model=list[HistoryMessage])
def chat_history(conversation_id: str, service: ChatService = Depends(get_chat_service)) -> list[HistoryMessage]:
    return service.history(conversation_id)


@router.post("/auto", response_model=AutoChatResponse)
async def auto_chat(request: AutoChatRequest, router: AutoRouter = Depends(get_auto_router)) -> AutoChatResponse:
    return await router.route_and_chat(request)

