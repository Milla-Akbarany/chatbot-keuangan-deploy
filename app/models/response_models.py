"""
app/models/response_models.py
Pydantic models untuk response API — konsisten di semua endpoint.
"""

from pydantic import BaseModel
from typing import Optional, List, Any
from datetime import datetime


class ChatResponse(BaseModel):
    session_id: str
    log_id: int
    intent: str
    confidence: float
    response: str
    needs_confirmation: bool = False
    pending_data: Optional[dict] = None  # data transaksi yang menunggu konfirmasi
    latency_ms: int


class TransactionItem(BaseModel):
    id: int
    tanggal: str
    deskripsi: str
    debit: Optional[float]
    kredit: Optional[float]
    jenis_akun: str
    sub_kategori: str


class TransactionListResponse(BaseModel):
    items: List[TransactionItem]
    total: int
    period: Optional[str] = None


class BalanceResponse(BaseModel):
    total_debit: float
    total_kredit: float
    saldo_bersih: float
    period: Optional[str] = None


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # detik


class ErrorResponse(BaseModel):
    error: str
    detail: Optional[str] = None
    log_id: Optional[int] = None


class HealthResponse(BaseModel):
    status: str
    mysql: str
    qdrant: str
    embedding_model: str
    timestamp: datetime
