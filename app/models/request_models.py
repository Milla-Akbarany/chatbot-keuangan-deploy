"""
app/models/request_models.py
Pydantic models untuk validasi request body dari API.
"""

from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    session_id: str = Field(..., description="UUID sesi percakapan")
    message: str = Field(..., min_length=1, max_length=500, description="Pesan dari user")

    class Config:
        json_schema_extra = {
            "example": {
                "session_id": "550e8400-e29b-41d4-a716-446655440000",
                "message": "catat beli makan siang 35 ribu"
            }
        }


class ConfirmRequest(BaseModel):
    session_id: str
    confirm: bool = Field(..., description="True jika user konfirmasi, False jika batal")


class UserFeedbackRequest(BaseModel):
    log_id: int
    helpful: bool = Field(..., description="True jika response membantu, False jika tidak")


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)
    full_name: Optional[str] = None
