import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.api.health import router as health_router
from app.api.scenarios import router as scenarios_router
from app.api.config_router import router as config_router
from app.api.clusters import router as clusters_router
from app.api.reports import router as reports_router
from app.api.auth import router as auth_router
from app.api.matches import router as matches_router
from app.api.assist import router as assist_router
from app.api.public import router as public_router
from app.api.alerts import router as alerts_router
from app.api.benchmark import router as benchmark_router
from app.api.demo import router as demo_router
from app.api.tracking import router as tracking_router

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
logger = logging.getLogger("relief_desk.api")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s v%s...", settings.PROJECT_NAME, settings.VERSION)
    logger.info("Gemini enabled: %s (Model: %s)", settings.GEMINI_ENABLED, settings.GEMINI_MODEL)
    logger.info("Demo mode: %s", settings.DEMO_MODE)
    yield
    logger.info("Shutting down %s...", settings.PROJECT_NAME)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="Multilingual crisis-reporting and coordination API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.API_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Root health check directly at /healthz as required by SETUP.md
app.include_router(health_router)
app.include_router(scenarios_router)
app.include_router(config_router)
app.include_router(clusters_router)
app.include_router(reports_router)
app.include_router(auth_router)
app.include_router(matches_router)
app.include_router(assist_router)
app.include_router(public_router)
app.include_router(alerts_router)
app.include_router(benchmark_router)
app.include_router(demo_router)
app.include_router(tracking_router)

@app.get("/")
def root():
    return {
        "app": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "docs_url": "/docs",
        "healthz": "/healthz"
    }
