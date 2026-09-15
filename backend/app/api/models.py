from fastapi import APIRouter, Depends

from app.models.schemas import CurrentModelResponse, ModelSelectionRequest
from app.services.model_service import ModelService

router = APIRouter(prefix="/models", tags=["models"])


def get_model_service() -> ModelService:
    from app.main import model_service
    return model_service


@router.post("/select", response_model=CurrentModelResponse)
def select_model(request: ModelSelectionRequest, service: ModelService = Depends(get_model_service)) -> CurrentModelResponse:
    return service.select(request)


@router.get("/current", response_model=CurrentModelResponse)
def current_model(service: ModelService = Depends(get_model_service)) -> CurrentModelResponse:
    return service.current()

