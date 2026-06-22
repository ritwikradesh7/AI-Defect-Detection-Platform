# Wires everything together: FastAPI app, CORS, the route modules, table creation on startup, and serving the frontend's index.html.

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .database import engine, Base
from .routes import auth_routes, image_routes, review_routes

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once before the server starts accepting requests."""
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)  
    logger.info("Database ready.")

    os.makedirs("uploads", exist_ok=True)
    os.makedirs("static", exist_ok=True)

    logger.info("DefectSense AI starting up.")
    yield
    logger.info("DefectSense AI shutting down.")


app = FastAPI(
    title       = "DefectSense AI - Defect Detection Platform",
    description = "Production line image analysis with AI-assisted defect detection, "
                  "human review queue, and role-based access control.",
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs",
    redoc_url   = "/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

app.include_router(auth_routes.router,   prefix="/api/auth",    tags=["Authentication"])
app.include_router(image_routes.router,  prefix="/api/images",  tags=["Images"])
app.include_router(review_routes.router, prefix="/api/reviews", tags=["Reviews"])


@app.get("/", include_in_schema=False)
def serve_frontend():
    frontend_path = "static/index.html"
    if os.path.exists(frontend_path):
        return FileResponse(frontend_path)
    return {"message": "DefectSense AI API is running!", "docs": "/docs"}


@app.get("/health", tags=["System"])
def health_check():
    return {"status": "healthy", "service": "DefectSense AI"}
