"""
app/utils/helpers.py
Fungsi utilitas yang dipakai di seluruh pipeline.

PERBAIKAN:
- Fix tanda +/- di format_transaction_list (debit=pemasukan=(+), kredit=pengeluaran=(-))
- Tambah fleksibilitas waktu: minggu ini/lalu, X bulan terakhir, kuartal, semester
- Tambah period_type "range" untuk rentang tanggal (digunakan di mysql_service)
"""

import re
from datetime import datetime, date, timedelta
from typing import Optional
from dataclasses import dataclass


# ── Preprocessing ────────────────────────────────────────────────────────────
def preprocess(text: str) -> str:
    """Normalisasi teks input: lowercase + strip whitespace berlebih."""
    return re.sub(r"\s+", " ", text.lower().strip())


# ── Temporal Parsing ─────────────────────────────────────────────────────────
@dataclass
class TemporalResult:
    period_type: str   # "month" | "year" | "daily" | "week" | "range" | "none"
    period_value: str  # "2025-01" | "2025" | "2025-01-15" | "2025-01-01:2025-03-31" | ""


BULAN_MAP = {
    "januari": "01", "februari": "02", "maret": "03", "april": "04",
    "mei": "05", "juni": "06", "juli": "07", "agustus": "08",
    "september": "09", "oktober": "10", "november": "11", "desember": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "ags": "08", "agt": "08",
    "sep": "09", "okt": "10", "nov": "11", "des": "12",
}

KUARTAL_MAP = {
    "1": ("01-01", "03-31"),
    "2": ("04-01", "06-30"),
    "3": ("07-01", "09-30"),
    "4": ("10-01", "12-31"),
}


def parse_temporal(text: str) -> TemporalResult:
    """
    Ekstrak informasi temporal dari teks natural language.

    Mendukung:
    - "bulan ini / bulan lalu"
    - "tahun ini / tahun lalu"
    - "hari ini / kemarin"
    - "minggu ini / minggu lalu"
    - "X bulan terakhir" (contoh: "3 bulan terakhir")
    - "kuartal 1/2/3/4"
    - "semester 1/2"
    - "januari 2025" / "januari" (nama bulan)
    - "YYYY-MM-DD" eksplisit
    """
    text_lower = text.lower()
    now = datetime.now()

    # ── Hari ────────────────────────────────────────────────────────────────
    if "hari ini" in text_lower:
        return TemporalResult("daily", now.strftime("%Y-%m-%d"))

    if "kemarin" in text_lower:
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        return TemporalResult("daily", yesterday)

    # ── Minggu ───────────────────────────────────────────────────────────────
    if "minggu ini" in text_lower:
        # Senin s/d Minggu minggu ini
        start = now - timedelta(days=now.weekday())
        end = start + timedelta(days=6)
        return TemporalResult(
            "range",
            f"{start.strftime('%Y-%m-%d')}:{end.strftime('%Y-%m-%d')}"
        )

    if "minggu lalu" in text_lower:
        start = now - timedelta(days=now.weekday() + 7)
        end = start + timedelta(days=6)
        return TemporalResult(
            "range",
            f"{start.strftime('%Y-%m-%d')}:{end.strftime('%Y-%m-%d')}"
        )

    # ── Bulan ────────────────────────────────────────────────────────────────
    if "bulan ini" in text_lower:
        return TemporalResult("month", now.strftime("%Y-%m"))

    # "X bulan terakhir"
    m = re.search(r"(\d+)\s*bulan\s*(?:terakhir|ke\s*belakang|lalu)", text_lower)
    if m:
        n = int(m.group(1))
        # Hitung bulan awal n bulan yang lalu
        month = now.month - n
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        try:
            start = now.replace(year=year, month=month, day=1)
        except ValueError:
            start = now.replace(year=year, month=month, day=28)
        return TemporalResult(
            "range",
            f"{start.strftime('%Y-%m-%d')}:{now.strftime('%Y-%m-%d')}"
        )
    
    if "bulan lalu" in text_lower:
        m = now.month - 1 if now.month > 1 else 12
        y = now.year if now.month > 1 else now.year - 1
        return TemporalResult("month", f"{y}-{m:02d}")


    # ── Tahun ────────────────────────────────────────────────────────────────
    if "tahun ini" in text_lower:
        return TemporalResult("year", str(now.year))

    if "tahun lalu" in text_lower:
        return TemporalResult("year", str(now.year - 1))

    # ── Kuartal ──────────────────────────────────────────────────────────────
    m = re.search(r"kuartal\s*([1-4])", text_lower)
    if m:
        q = m.group(1)
        start_dd, end_dd = KUARTAL_MAP[q]
        # Cek apakah ada tahun disebutkan
        yr_match = re.search(r"\b(\d{4})\b", text_lower)
        year = int(yr_match.group(1)) if yr_match else now.year
        return TemporalResult(
            "range",
            f"{year}-{start_dd}:{year}-{end_dd}"
        )

    # ── Semester ─────────────────────────────────────────────────────────────
    m = re.search(r"semester\s*([12])", text_lower)
    if m:
        s = m.group(1)
        yr_match = re.search(r"\b(\d{4})\b", text_lower)
        year = int(yr_match.group(1)) if yr_match else now.year
        if s == "1":
            return TemporalResult("range", f"{year}-01-01:{year}-06-30")
        else:
            return TemporalResult("range", f"{year}-07-01:{year}-12-31")

    # ── Nama Bulan + Tahun ───────────────────────────────────────────────────
    for nama_bulan, num_bulan in BULAN_MAP.items():
        pattern = rf"{nama_bulan}\s+(\d{{4}})"
        m = re.search(pattern, text_lower)
        if m:
            return TemporalResult("month", f"{m.group(1)}-{num_bulan}")

    # ── Nama Bulan saja → pakai tahun ini ────────────────────────────────────
    for nama_bulan, num_bulan in BULAN_MAP.items():
        if re.search(rf"\b{nama_bulan}\b", text_lower):
            return TemporalResult("month", f"{now.year}-{num_bulan}")

    # ── Tahun eksplisit ───────────────────────────────────────────────────────
    m = re.search(r"\b(20\d{2})\b", text_lower)
    if m:
        return TemporalResult("year", m.group(1))

    # ── Tanggal eksplisit YYYY-MM-DD ─────────────────────────────────────────
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if m:
        return TemporalResult("daily", m.group(0))

    return TemporalResult("none", "")


def describe_period(temporal: TemporalResult) -> str:
    """Ubah TemporalResult menjadi teks yang mudah dibaca manusia."""
    if temporal.period_type == "month":
        return f"bulan {temporal.period_value}"
    elif temporal.period_type == "year":
        return f"tahun {temporal.period_value}"
    elif temporal.period_type == "daily":
        return f"tanggal {temporal.period_value}"
    elif temporal.period_type == "range":
        parts = temporal.period_value.split(":")
        if len(parts) == 2:
            return f"{parts[0]} s/d {parts[1]}"
    return "semua waktu"


# ── Nominal Parsing ──────────────────────────────────────────────────────────
def parse_amount(text: str) -> Optional[float]:
    text_lower = text.lower().strip()
    
    # Ganti koma desimal ke titik dulu (1,8jt → 1.8jt)
    text_lower = re.sub(r"(\d),(\d)", r"\1.\2", text_lower)
    # Baru hapus titik ribuan (1.800.000 → 1800000), 
    # tapi hati-hati jangan hapus titik desimal
    text_lower = re.sub(r"(\d)\.(\d{3})", r"\1\2", text_lower)

    patterns = [
        (r"(\d+(?:\.\d+)?)\s*juta",  1_000_000),
        (r"(\d+(?:\.\d+)?)\s*jt",    1_000_000),
        (r"(\d+(?:\.\d+)?)\s*ribu",  1_000),
        (r"(\d+(?:\.\d+)?)\s*rbu",   1_000),
        (r"(\d+(?:\.\d+)?)\s*rb",    1_000),
        (r"(\d+(?:\.\d+)?)\s*k\b",   1_000),
        (r"\brp\s*(\d+)",             1),
    ]
    
    for pattern, multiplier in patterns:
        m = re.search(pattern, text_lower)
        if m:
            return float(m.group(1)) * multiplier

    # Angka murni >= 1000
    m = re.search(r"\b(\d{4,})\b", text_lower)
    if m:
        return float(m.group(1))

    return None


# ── Deskripsi Cleaning ───────────────────────────────────────────────────────
_STOPWORDS = {
    "catat", "bayar", "beli", "transfer", "keluar",
    "pengeluaran", "pemasukan", "masuk", "tadi", "kemarin", "hari",
    "ini", "pagi", "siang", "malam", "sore", "bulan", "tahun",
    "ribu", "juta", "rb", "jt", "k", "rp", "rupiah",
    "abis", "habis", "udah", "udh", "dah",
}
_MONTH_WORDS = set(BULAN_MAP.keys())


def extract_description(text: str) -> str:
    """
    Ekstrak deskripsi bersih dari teks transaksi.
    Menghapus kata perintah, nominal, satuan, dan kata temporal.
    """
    text = preprocess(text)
    # Hapus nominal + satuan
    text = re.sub(r"\b\d+(?:[.,]\d+)?\s*(?:juta|jt|ribu|rbu|rb|k|rp|rupiah)?\b", "", text)
    # Hapus angka murni
    text = re.sub(r"\b\d+\b", "", text)
    # Hapus stopwords dan kata bulan
    words = text.split()
    words = [w for w in words if w not in _STOPWORDS and w not in _MONTH_WORDS]
    result = " ".join(words).strip()
    return result.capitalize() if result else "Transaksi"


# ── Response Formatting ──────────────────────────────────────────────────────
def format_currency(amount: float) -> str:
    """Format angka ke format Rupiah Indonesia."""
    return f"Rp {amount:,.0f}".replace(",", ".")


def format_transaction_list(rows: list) -> str:
    """
    Format daftar transaksi untuk ditampilkan di chat.

    PERBAIKAN:
    - debit > 0 = pemasukan = tanda (+) ✅
    - kredit > 0 = pengeluaran = tanda (-) ✅
    (sebelumnya tanda +/- terbalik)
    """
    if not rows:
        return "Tidak ada transaksi yang ditemukan."

    lines = []
    for row in rows[:10]:  # Batasi tampilan maksimal 10 item
        tgl = str(row.get("tanggal", ""))[:10]
        desk = row.get("deskripsi", "-")
        debit = float(row.get("debit", 0) or 0)
        kredit = float(row.get("kredit", 0) or 0)

        if debit > 0:
            # Pemasukan / income
            tipe = "(+)"
            nominal = debit
        else:
            # Pengeluaran / expense
            tipe = "(-)"
            nominal = kredit

        jenis = row.get("sub_kategori", "")
        jenis_str = f" [{jenis}]" if jenis else ""
        lines.append(f"• {tgl} | {desk}{jenis_str} | {tipe} {format_currency(nominal)}")

    result = "\n".join(lines)
    if len(rows) > 10:
        result += f"\n... dan {len(rows) - 10} transaksi lainnya."
    return result
