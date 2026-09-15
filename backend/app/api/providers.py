from fastapi import APIRouter, Depends, status

from app.models.schemas import ConnectRequest, ConnectResponse, ProviderId, ProviderStatus, ModelInfo
from app.services.provider_service import ProviderService

router = APIRouter(prefix="/providers", tags=["providers"])


def get_provider_service() -> ProviderService:
    from app.main import provider_service
    return provider_service


@router.get("", response_model=list[ProviderStatus])
def list_providers(service: ProviderService = Depends(get_provider_service)) -> list[ProviderStatus]:
    return service.list()


@router.post("/connect", response_model=ConnectResponse)
async def connect_provider(request: ConnectRequest, service: ProviderService = Depends(get_provider_service)) -> ConnectResponse:
    return await service.connect(request)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
def disconnect_provider(provider: ProviderId, service: ProviderService = Depends(get_provider_service)) -> None:
    service.disconnect(provider)


@router.post("/{provider}/refresh_models", response_model=list[ModelInfo])
async def refresh_models(provider: ProviderId, service: ProviderService = Depends(get_provider_service)) -> list[ModelInfo]:
    return await service.refresh_models(provider)

