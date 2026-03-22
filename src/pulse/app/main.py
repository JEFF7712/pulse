from typing import Annotated

from fastapi import Depends, FastAPI

from pulse.app.config import Settings
from pulse.app.dependencies import get_settings


def create_app() -> FastAPI:
    app = FastAPI()

    @app.get("/health")
    def health(_settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
        return {"status": "ok"}

    return app
