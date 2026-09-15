from __future__ import annotations

from app.errors import AppError, ModelNotFoundError
from app.models.schemas import CurrentModelResponse, ModelInfo, ModelSelectionRequest
from app.services.provider_service import ProviderService
from app.services.storage_service import StorageService


class ModelService:
    def __init__(self, storage: StorageService, providers: ProviderService) -> None:
        self.storage = storage
        self.providers = providers

    def select(self, request: ModelSelectionRequest) -> CurrentModelResponse:
        if not any(item.id == request.model for item in self.storage.get_models(request.provider)):
            raise ModelNotFoundError(request.provider.value, request.model)
        self.storage.select_model(request.provider, request.model)
        return CurrentModelResponse(provider=request.provider, model=request.model)

    def current(self) -> CurrentModelResponse:
        selected = self.storage.current_model()
        if not selected:
            raise AppError("No model has been selected", 404, "no_model_selected")
        return CurrentModelResponse(provider=selected["provider"], model=selected["model"])

    def ensure_available(self, provider_id, model: str) -> ModelInfo:
        for item in self.storage.get_models(provider_id):
            if item.id == model:
                return item
        raise ModelNotFoundError(provider_id.value, model)

