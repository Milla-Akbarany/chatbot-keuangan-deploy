"""
app/api/chat.py
Endpoint utama chatbot.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException

from app.models.request_models import ChatRequest, ConfirmRequest, UserFeedbackRequest
from app.models.response_models import ChatResponse
from app.services.chatbot_service import process_message, process_confirmation
from app.services.mysql_service import update_feedback
from app.api.auth import get_current_user

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("/message", response_model=ChatResponse)
def send_message(req: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Kirim pesan ke chatbot.
    Semua pesan diproses melalui pipeline penuh:
    preprocess → embed → intent classify → entity resolve → route → log
    """
    result = process_message(
        user_input=req.message,
        session_id=req.session_id,
        user_id=current_user["user_id"],
    )
    return ChatResponse(
        session_id=req.session_id,
        log_id=result.log_id,
        intent=result.intent,
        confidence=result.confidence,
        response=result.response,
        needs_confirmation=result.needs_confirmation,
        pending_data=result.pending_data,
        latency_ms=result.latency_ms,
    )


@router.post("/confirm")
def confirm_transaction(req: ConfirmRequest, current_user: dict = Depends(get_current_user)):
    """
    Konfirmasi atau batalkan transaksi yang pending.
    Dipanggil setelah user menjawab 'ya' atau 'batal'.
    """
    result = process_confirmation(
        session_id=req.session_id,
        user_id=current_user["user_id"],
        confirm=req.confirm,
    )
    return {"response": result.response, "latency_ms": result.latency_ms}


@router.post("/feedback")
def submit_feedback(req: UserFeedbackRequest, current_user: dict = Depends(get_current_user)):
    """Simpan feedback user (thumbs up/down) untuk evaluasi sistem."""
    update_feedback(req.log_id, req.helpful)
    return {"message": "Feedback berhasil disimpan."}


@router.get("/session/new")
def new_session():
    """Generate session ID baru untuk memulai percakapan."""
    return {"session_id": str(uuid.uuid4())}
