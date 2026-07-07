"""
app/utils/prompts.py
Template prompt untuk Groq LLM.
Dipisah dari llm_service agar mudah diubah tanpa menyentuh logika service.

PERBAIKAN:
- Ditambahkan prompt spesifik per intent
- System prompt lebih ketat agar LLM tidak halusinasi angka
- User prompt menyertakan data dari database sebagai konteks
"""

from typing import Optional


def build_system_prompt() -> str:
    return """Kamu adalah asisten keuangan pribadi yang membantu pengguna mencatat
dan menganalisis transaksi keuangan mereka.

Aturan WAJIB:
1. Jawab dalam Bahasa Indonesia yang ramah dan ringkas.
2. JANGAN pernah mengarang atau mengasumsikan angka — hanya gunakan data yang diberikan.
3. Jika data tidak tersedia, katakan dengan jelas bahwa data tidak ditemukan.
4. Maksimum 3-4 kalimat per jawaban kecuali diminta lebih.
5. Fokus pada informasi yang ditanya — jangan tambah informasi yang tidak diminta.
6. Gunakan format Rupiah untuk nominal (contoh: Rp 1.500.000).
7. Berikan insight atau saran singkat jika memungkinkan berdasarkan data yang ada."""


def build_user_prompt(
    user_input: str,
    intent: str,
    context_data: Optional[dict] = None,
) -> str:
    """
    Bangun prompt berdasarkan intent dan data konteks dari database.
    Angka eksak sudah diambil dari MySQL — LLM hanya memformat respons secara natural.
    """
    # Pilih prompt builder berdasarkan intent
    builders = {
        "greeting": _build_greeting_prompt,
        "tanya_saldo": _build_saldo_prompt,
        "tanya_total_akun": _build_total_prompt,
        "tanya_total_kategori": _build_total_prompt,
        "lihat_rincian": _build_rincian_prompt,
        "unknown": _build_unknown_prompt,
    }

    builder = builders.get(intent, _build_default_prompt)
    return builder(user_input, intent, context_data)


# ── Prompt Builders per Intent ───────────────────────────────────────────────

def _build_greeting_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    return f"""Pengguna menyapa: "{user_input}"

Berikan sapaan ramah sebagai asisten keuangan. Sebutkan secara singkat 
apa saja yang bisa kamu bantu (catat transaksi, cek saldo, lihat rincian, 
hitung total). Jangan terlalu panjang, cukup 2-3 kalimat."""


def _build_saldo_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    if not context_data:
        return f"""Pengguna bertanya: "{user_input}"
Data saldo tidak tersedia. Sampaikan dengan sopan bahwa data tidak ditemukan."""

    return f"""Pengguna bertanya: "{user_input}"

Data saldo dari database (GUNAKAN ANGKA INI, JANGAN DIUBAH):
- Total Pemasukan: {context_data.get('total_debit', 0)}
- Total Pengeluaran: {context_data.get('total_kredit', 0)}
- Saldo Bersih: {context_data.get('saldo', 0)}
- Periode: {context_data.get('periode', 'Semua waktu')}

Sampaikan informasi saldo ini secara natural dan ramah. 
Gunakan emoji yang sesuai (💰, 📊, 📈, 📉).
Tambahkan insight singkat, misalnya apakah pengeluaran lebih besar dari pemasukan."""


def _build_total_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    if not context_data:
        return f"""Pengguna bertanya: "{user_input}"
Data total tidak tersedia. Sampaikan dengan sopan."""

    return f"""Pengguna bertanya: "{user_input}"

Data dari database (GUNAKAN ANGKA INI, JANGAN DIUBAH):
- Total: {context_data.get('total', 0)}
- Jenis Akun: {context_data.get('jenis_akun', '-')}
- Sub Kategori: {context_data.get('sub_kategori', '-')}
- Periode: {context_data.get('periode', 'Semua waktu')}

Sampaikan informasi total ini secara natural dan ramah.
Gunakan emoji yang sesuai."""


def _build_rincian_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    if not context_data or not context_data.get("transaksi"):
        return f"""Pengguna bertanya: "{user_input}"
Tidak ada transaksi yang ditemukan. Sampaikan dengan sopan."""

    transaksi_str = context_data.get("transaksi_formatted", "Tidak ada data")
    jumlah = context_data.get("jumlah_transaksi", 0)

    return f"""Pengguna bertanya: "{user_input}"

Data transaksi dari database (total {jumlah} transaksi):
{transaksi_str}

Periode: {context_data.get('periode', 'Semua waktu')}

Berikan ringkasan singkat dari transaksi di atas.
Sebutkan jumlah transaksi yang ditemukan dan periode waktunya.
JANGAN mengubah angka, gunakan persis seperti data di atas.
Tampilkan daftar transaksi, lalu tambahkan ringkasan singkat di akhir."""


def _build_unknown_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    return f"""Pengguna berkata: "{user_input}"

Saya tidak bisa mengenali maksud pengguna secara spesifik.
Jawab sebaik mungkin sebagai asisten keuangan yang ramah.
Jika pertanyaan di luar topik keuangan, arahkan kembali dengan sopan 
ke topik keuangan dan sebutkan fitur yang tersedia:
- Catat transaksi (contoh: "catat beli makan 35 ribu")
- Cek saldo (contoh: "cek saldo bulan ini")
- Lihat rincian transaksi (contoh: "lihat transaksi bulan ini")
- Hitung total per kategori (contoh: "total makan bulan ini")"""


def _build_default_prompt(
    user_input: str, intent: str, context_data: Optional[dict] = None
) -> str:
    context_str = ""
    if context_data:
        context_str = f"\n\nData dari database:\n{_format_context(context_data)}"

    return f"""Permintaan pengguna: "{user_input}"
Intent yang terdeteksi: {intent}{context_str}

Berikan respons yang sesuai berdasarkan data di atas."""


def _format_context(data: dict) -> str:
    lines = []
    for key, value in data.items():
        lines.append(f"- {key}: {value}")
    return "\n".join(lines)
