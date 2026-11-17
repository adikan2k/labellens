import platform

from fastapi import FastAPI

from api.app.schemas import Health, Source, Versions

API_VERSION = "0.1.0"

app = FastAPI(title="LabelLens API", version=API_VERSION)


@app.get("/health")
def health() -> Health:
    return Health(
        status="ok",
        versions=Versions(api=API_VERSION, python=platform.python_version()),
        source=Source(),
    )
