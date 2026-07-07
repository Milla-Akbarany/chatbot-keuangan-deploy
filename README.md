# Chatbot Keuangan — Backend API + UI

Sistem chatbot pencatatan keuangan dengan arsitektur hybrid:
**FastAPI** (backend) + **MySQL** (transaksi) + **Qdrant** (semantic retrieval) + **Groq** (LLM) + **Streamlit** (UI)

---

## Struktur Project

```
project/
├── app/
│   ├── main.py                  # FastAPI app, startup, routing
│   ├── api/
│   │   ├── auth.py              # Register, login, JWT
│   │   ├── chat.py              # Endpoint chatbot utama
│   │   └── transaction.py       # Endpoint data transaksi (untuk dashboard)
│   ├── services/
│   │   ├── chatbot_service.py   # Orchestrator pipeline utama
│   │   ├── embedding_service.py # SentenceTransformer (singleton)
│   │   ├── qdrant_service.py    # Intent classify + entity resolve
│   │   ├── mysql_service.py     # Semua operasi MySQL + logging
│   │   └── llm_service.py       # Groq LLM (natural language generation)
│   ├── models/
│   │   ├── request_models.py    # Pydantic request validation
│   │   └── response_models.py   # Pydantic response schemas
│   ├── utils/
│   │   ├── helpers.py           # Preprocess, parse tanggal, parse nominal
│   │   └── prompts.py           # Template prompt untuk Groq
│   └── config/
│       └── settings.py          # Semua config dari .env
├── setup/
│   └── seed_data.py             # Script setup awal (jalankan sekali)
├── streamlit_ui/
│   └── app.py                   # UI Streamlit
├── data/                        # CSV referensi
├── .env.example                 # Template environment variables
├── requirements.txt
└── run.py                       # Entry point server
```

---

## Alur Pipeline

```
User Input (Streamlit)
      │ HTTP POST /chat/message
      ▼
FastAPI → chatbot_service.process_message()
      │
      ├─ preprocess(text)
      │
      ├─ embed(text)                     → SentenceTransformer
      │
      ├─ classify_intent(vector)         → Qdrant: data_intent
      │    Semua input melalui classifier (tidak ada bypass)
      │
      ├─ resolve_entity(vector, text)    → Qdrant: dict_user (1 panggilan)
      │    Hasilkan jenis_akun + sub_kategori sekaligus
      │
      ├─ parse_temporal(text)            → extract periode waktu
      │
      ├─ _route(intent, ...)             → handler sesuai intent
      │    catat_transaksi → MySQL INSERT (setelah konfirmasi)
      │    tanya_saldo     → MySQL SUM
      │    tanya_total_*   → MySQL SUM dengan filter
      │    lihat_rincian   → MySQL SELECT
      │    greeting/help   → static response
      │    unknown         → fallback response
      │
      └─ write_query_log(...)            → MySQL: query_log (WAJIB, setiap request)
```

---

## Instalasi

### 1. Prasyarat

- Python 3.11+
- MySQL 8.0+ (atau PlanetScale)
- Docker (untuk Qdrant)
- Akun Groq (https://console.groq.com)

### 2. Clone dan setup environment

```bash
git clone <repo-url>
cd project

# Buat virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# atau: venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Konfigurasi `.env`

```bash
cp .env.example .env
# Edit .env dengan kredensial Anda
nano .env
```

Isi minimal yang wajib diisi:
```
MYSQL_PASSWORD=password_mysql_anda
GROQ_API_KEY=gsk_xxx
JWT_SECRET_KEY=string_acak_panjang_minimal_32_karakter
```

### 4. Jalankan Qdrant dengan Docker

```bash
docker run -d \
  --name qdrant_local \
  -p 6333:6333 \
  -v qdrant_storage:/qdrant/storage \
  qdrant/qdrant:latest
```

### 5. Buat database MySQL

```sql
CREATE DATABASE data_finance CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 6. Setup awal (jalankan SEKALI)

```bash
python setup/seed_data.py
```

Script ini akan:
- Membuat semua tabel MySQL
- Membuat koleksi Qdrant
- Upload intent samples ke Qdrant
- Upload dict_user ke Qdrant
- Seed data referensi ke MySQL

### 7. Jalankan backend

```bash
python run.py
```

Server berjalan di: http://localhost:8000
Dokumentasi API: http://localhost:8000/docs

### 8. Jalankan UI Streamlit (terminal terpisah)

```bash
streamlit run streamlit_ui/app.py
```

UI berjalan di: http://localhost:8501

---

## Penggunaan API

### Register

```bash
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"user1","password":"pass123","full_name":"User Pertama"}'
```

### Login

```bash
curl -X POST http://localhost:8000/auth/login \
  -d "username=user1&password=pass123"
# Simpan access_token dari response
```

### Kirim pesan ke chatbot

```bash
curl -X POST http://localhost:8000/chat/message \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"uuid-session","message":"catat beli makan siang 35 ribu"}'
```

### Konfirmasi transaksi

```bash
curl -X POST http://localhost:8000/chat/confirm \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"uuid-session","confirm":true}'
```

---

## Perbedaan dengan Prototype Lama

| Aspek | Prototype Lama | Pipeline Baru |
|---|---|---|
| Intent bypass | `if text.startswith("catat")` → bypass Qdrant | Semua melalui classifier |
| Panggilan Qdrant per request | 3x ke collection yang sama | 1x (cached per request) |
| Point ID di Qdrant | `timestamp()` — rawan collision | UUID4 |
| Credentials | Hardcoded di kode | `.env` file |
| SQL | String concatenation | Parameterized query |
| Logging | Tidak ada | `query_log` — setiap request |
| Auth | Tidak ada | JWT (register/login) |
| LLM | Diinisialisasi, tidak dipanggil | Dipanggil hanya untuk NLG |
| Error handling | Minimal | Try-catch + `response_type` |
| UI | Gradio (lokal) | Streamlit → FastAPI (bisa deploy) |

---

## Catatan untuk Riset

- Threshold `THRESHOLD_INTENT` dan `THRESHOLD_ENTITY` di `.env` harus ditentukan secara empiris melalui precision-recall curve pada validation set (lihat dokumen analisis riset)
- Semua data eksperimen tersimpan di tabel `query_log` — gunakan untuk analisis post-hoc
- Untuk evaluasi, query: `SELECT predicted_intent, response_type, COUNT(*) FROM query_log GROUP BY 1,2`
