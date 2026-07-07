"""
app/main.py
FastAPI application — entry point untuk seluruh backend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from datetime import datetime

from app.api import chat, auth, transaction
from app.services import qdrant_service, mysql_service, embedding_service
from app.models.response_models import HealthResponse
from app.config.settings import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: inisialisasi semua service sebelum menerima request.
    Shutdown: cleanup jika diperlukan.
    """
    print("🚀 Startup: menginisialisasi services...")

    # 1. Init schema MySQL
    mysql_service.init_schema()
    print("✅ MySQL schema siap.")

    # 2. Pastikan koleksi Qdrant ada
    qdrant_service.ensure_collections()
    print("✅ Qdrant collections siap.")

    # 3. Pre-load embedding model (agar request pertama tidak lambat)
    embedding_service.get_model()
    print("✅ Embedding model dimuat.")

    print("🎯 Server siap menerima request.")
    yield

    print("👋 Shutdown.")


app = FastAPI(
    title="Chatbot Keuangan API",
    description="Backend API untuk sistem chatbot pencatatan keuangan berbasis semantic retrieval.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — sesuaikan origins untuk production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.debug else ["https://your-frontend-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(transaction.router)


@app.get("/health", response_model=HealthResponse, tags=["system"])
def health_check():
    """Cek status semua komponen sistem."""
    return HealthResponse(
        status="ok",
        mysql="ok",  # Jika sampai sini, MySQL sudah terhubung saat startup
        qdrant=qdrant_service.check_health(),
        embedding_model=settings.embedding_model,
        timestamp=datetime.utcnow(),
    )


@app.get("/", tags=["system"])
def root():
    return {
        "message": "Chatbot Keuangan API",
        "docs": "/docs",
        "health": "/health",
    }
