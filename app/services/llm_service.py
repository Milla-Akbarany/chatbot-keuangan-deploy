"""
app/services/llm_service.py
Integrasi Groq LLM.

Catatan penting:
- LLM di sini dipanggil HANYA untuk response yang butuh natural language generation.
- Untuk query angka eksak (saldo, total), JANGAN pakai LLM — gunakan template saja.
  LLM bisa halusinasi angka. MySQL adalah source of truth untuk angka keuangan.
- LLM dipakai untuk: ringkasan, saran, analisis tren (bukan angka eksak).
"""

from groq import Groq
from typing import Optional
from app.config.settings import get_settings
from app.utils.prompts import build_system_prompt, build_user_prompt
import logging
import time

logger = logging.getLogger(__name__)
settings = get_settings()

_client: Optional[Groq] = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=settings.groq_api_key)
    return _client


def generate_response(
    user_input: str,
    intent: str,
    context_data: Optional[dict] = None,
    max_tokens: int = 300,
) -> tuple[str, int]:
    """
    Generate response natural language menggunakan Groq.
    Hanya dipanggil untuk intent yang membutuhkan NLG (bukan angka eksak).

    Return: (response_text, latency_ms)
    """
    t0 = time.time()
    client = get_client()

    system_prompt = build_system_prompt()
    user_prompt = build_user_prompt(user_input, intent, context_data)

    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=max_tokens,
            temperature=0.3,   # rendah agar deterministik untuk domain keuangan
        )
        response = completion.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Groq API error: {e}")
        response = "Maaf, saya mengalami kendala teknis. Silakan coba lagi."

    latency_ms = int((time.time() - t0) * 1000)
    return response, latency_ms


def check_health() -> str:
    try:
        get_client()
        return "ok"
    except Exception as e:
        return f"error: {e}"
