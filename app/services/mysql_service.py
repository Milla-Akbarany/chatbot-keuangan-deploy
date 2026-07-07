"""
app/services/mysql_service.py
Semua operasi ke MySQL.
- Koneksi via connection pool
- Semua query parameterized
- Logging setiap request ke tabel query_log

PERBAIKAN:
- Tambah support period_type "range" (untuk minggu, kuartal, semester, X bulan terakhir)
  Format period_value untuk range: "YYYY-MM-DD:YYYY-MM-DD"
"""

import mysql.connector
from mysql.connector import pooling
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.config.settings import get_settings
import logging

logger = logging.getLogger(__name__)
settings = get_settings()

# ── Connection Pool ──────────────────────────────────────────────────────────
_pool: Optional[pooling.MySQLConnectionPool] = None



def get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="chatbot_pool",
            pool_size=5,
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            database=settings.mysql_database,
            charset="utf8mb4",
            autocommit=False,
        )
    return _pool


def get_connection():
    return get_pool().get_connection()


# ── Schema Inisialisasi ──────────────────────────────────────────────────────
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INT AUTO_INCREMENT PRIMARY KEY,
    username   VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name  VARCHAR(100),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS data_transaksi (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    user_id     INT NOT NULL,
    tanggal     DATE NOT NULL,
    deskripsi   VARCHAR(255),
    debit       DECIMAL(15,2) DEFAULT 0,
    kredit      DECIMAL(15,2) DEFAULT 0,
    jenis_akun  VARCHAR(50),
    sub_kategori VARCHAR(50),
    created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS intents (
    intent_id   INT PRIMARY KEY,
    intent_name VARCHAR(50) NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS actions (
    action_id   INT PRIMARY KEY,
    action_name VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS intent_action_map (
    map_id      INT AUTO_INCREMENT PRIMARY KEY,
    intent_id   INT,
    action_id   INT,
    FOREIGN KEY (intent_id) REFERENCES intents(intent_id),
    FOREIGN KEY (action_id) REFERENCES actions(action_id)
);

CREATE TABLE IF NOT EXISTS dict_user (
    id           INT AUTO_INCREMENT PRIMARY KEY,
    keyword      VARCHAR(100),
    jenis_akun   VARCHAR(50),
    sub_kategori VARCHAR(50),
    sinonim      TEXT
);

CREATE TABLE IF NOT EXISTS query_log (
    log_id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id                 INT,
    session_id              VARCHAR(36) NOT NULL,
    request_ts              DATETIME(3) NOT NULL,
    user_input              TEXT NOT NULL,
    preprocessed_input      TEXT,
    predicted_intent        VARCHAR(50),
    intent_confidence       FLOAT,
    intent_threshold_used   FLOAT,
    intent_detected_via     VARCHAR(20),
    detected_jenis_akun     VARCHAR(30),
    detected_sub_kategori   VARCHAR(50),
    entity_confidence       FLOAT,
    entity_detected_via     VARCHAR(20),
    period_type             VARCHAR(10),
    period_value            VARCHAR(30),
    generated_sql           TEXT,
    sql_success             TINYINT(1),
    sql_rows_affected       INT,
    response_text           TEXT,
    response_type           VARCHAR(30),
    latency_total_ms        INT,
    latency_embed_ms        INT,
    latency_qdrant_ms       INT,
    latency_sql_ms          INT,
    user_feedback           TINYINT,
    feedback_ts             DATETIME,
    model_version           VARCHAR(50),
    threshold_version       VARCHAR(100),
    INDEX idx_session  (session_id),
    INDEX idx_ts       (request_ts),
    INDEX idx_intent   (predicted_intent),
    INDEX idx_rtype    (response_type)
);
INSERT IGNORE INTO intents (intent_id, intent_name, description) VALUES
    (1, 'greeting',             'Sapaan pengguna'),
    (2, 'help',                 'Permintaan bantuan'),
    (3, 'catat_transaksi',      'Mencatat transaksi'),
    (4, 'tanya_saldo',          'Menanyakan saldo'),
    (5, 'tanya_total_akun',     'Menanyakan total per akun'),
    (6, 'tanya_total_kategori', 'Menanyakan total per kategori'),
    (7, 'lihat_rincian',        'Melihat rincian transaksi'),
    (8, 'unknown',              'Intent tidak dikenali'),
    (9, 'hapus_transaksi',      'Menghapus transaksi');
"""


def init_schema():
    conn = get_connection()
    cursor = conn.cursor()
    for stmt in SCHEMA_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt and not stmt.startswith("--"):
            try:
                cursor.execute(stmt)
            except Exception as e:
                logger.warning(f"Schema stmt skipped: {e}")
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Schema MySQL berhasil diinisialisasi.")

# ── Helper: build period filter ───────────────────────────────────────────────
def _apply_period_filter(
    sql: str,
    params: list,
    period_type: Optional[str],
    period_value: Optional[str],
) -> tuple[str, list]:
    """
    Tambahkan filter periode ke query SQL.
    Mendukung: month, year, daily, range.

    range format: "YYYY-MM-DD:YYYY-MM-DD"
    """
    if not period_type or not period_value:
        return sql, params

    if period_type == "month":
        sql += " AND DATE_FORMAT(tanggal, '%Y-%m') = %s"
        params.append(period_value)

    elif period_type == "year":
        sql += " AND YEAR(tanggal) = %s"
        params.append(period_value)

    elif period_type == "daily":
        sql += " AND tanggal = %s"
        params.append(period_value)

    elif period_type == "range" and ":" in period_value:
        parts = period_value.split(":")
        if len(parts) == 2:
            sql += " AND tanggal BETWEEN %s AND %s"
            params.extend(parts)

    return sql, params


# ── Query Transaksi ──────────────────────────────────────────────────────────
def get_transactions(
    user_id: int,
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
    jenis_akun: Optional[str] = None,
    sub_kategori: Optional[str] = None,
    limit: int = 50,
) -> tuple:
    """Ambil daftar transaksi dengan filter opsional."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    base_sql = "SELECT * FROM data_transaksi WHERE user_id = %s"
    params: List[Any] = [user_id]

    # Terapkan filter periode
    base_sql, params = _apply_period_filter(base_sql, params, period_type, period_value)

    if jenis_akun:
        base_sql += " AND jenis_akun = %s"
        params.append(jenis_akun)

    if sub_kategori:
        base_sql += " AND sub_kategori = %s"
        params.append(sub_kategori)

    base_sql += " ORDER BY tanggal DESC LIMIT %s"
    params.append(limit)

    cursor.execute(base_sql, params)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows, base_sql


def get_total(
    user_id: int,
    kolom: str,  # "debit" atau "kredit"
    period_type: Optional[str] = None,
    period_value: Optional[str] = None,
    jenis_akun: Optional[str] = None,
    sub_kategori: Optional[str] = None,
) -> tuple:
    """Hitung total debit atau kredit dengan filter."""
    if kolom not in ("debit", "kredit"):
        raise ValueError("kolom harus 'debit' atau 'kredit'")

    conn = get_connection()
    cursor = conn.cursor()

    base_sql = f"SELECT COALESCE(SUM({kolom}), 0) FROM data_transaksi WHERE user_id = %s"
    params: List[Any] = [user_id]

    # Terapkan filter periode
    base_sql, params = _apply_period_filter(base_sql, params, period_type, period_value)

    if jenis_akun:
        base_sql += " AND jenis_akun = %s"
        params.append(jenis_akun)

    if sub_kategori:
        base_sql += " AND sub_kategori = %s"
        params.append(sub_kategori)

    cursor.execute(base_sql, params)
    result = cursor.fetchone()[0]
    cursor.close()
    conn.close()
    return float(result), base_sql


def insert_transaction(user_id: int, data: Dict[str, Any]) -> int:
    """Simpan transaksi baru. Return ID transaksi yang baru dibuat."""
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO data_transaksi
            (user_id, tanggal, deskripsi, debit, kredit, jenis_akun, sub_kategori)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        user_id,
        data["tanggal"],
        data["deskripsi"],
        data.get("debit", 0),
        data.get("kredit", 0),
        data.get("jenis_akun", ""),
        data.get("sub_kategori", ""),
    )
    cursor.execute(sql, params)
    conn.commit()
    new_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return new_id


# ── Logging ──────────────────────────────────────────────────────────────────
def write_query_log(log_data: Dict[str, Any]) -> int:
    """
    Tulis satu baris ke query_log.
    Return log_id yang baru dibuat.
    """
    conn = get_connection()
    cursor = conn.cursor()

    sql = """
        INSERT INTO query_log (
            user_id, session_id, request_ts, user_input, preprocessed_input,
            predicted_intent, intent_confidence, intent_threshold_used, intent_detected_via,
            detected_jenis_akun, detected_sub_kategori, entity_confidence, entity_detected_via,
            period_type, period_value,
            generated_sql, sql_success, sql_rows_affected,
            response_text, response_type,
            latency_total_ms, latency_embed_ms, latency_qdrant_ms, latency_sql_ms,
            model_version, threshold_version
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s
        )
    """
    params = (
        log_data.get("user_id"),
        log_data.get("session_id"),
        log_data.get("request_ts", datetime.utcnow()),
        log_data.get("user_input"),
        log_data.get("preprocessed_input"),
        log_data.get("predicted_intent"),
        log_data.get("intent_confidence"),
        log_data.get("intent_threshold_used"),
        log_data.get("intent_detected_via"),
        log_data.get("detected_jenis_akun"),
        log_data.get("detected_sub_kategori"),
        log_data.get("entity_confidence"),
        log_data.get("entity_detected_via"),
        log_data.get("period_type"),
        log_data.get("period_value"),
        log_data.get("generated_sql"),
        log_data.get("sql_success"),
        log_data.get("sql_rows_affected"),
        log_data.get("response_text"),
        log_data.get("response_type"),
        log_data.get("latency_total_ms"),
        log_data.get("latency_embed_ms"),
        log_data.get("latency_qdrant_ms"),
        log_data.get("latency_sql_ms"),
        log_data.get("model_version"),
        log_data.get("threshold_version"),
    )
    cursor.execute(sql, params)
    conn.commit()
    log_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return log_id


def update_feedback(log_id: int, helpful: bool):
    """Update kolom user_feedback setelah user memberi rating."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE query_log SET user_feedback = %s, feedback_ts = %s WHERE log_id = %s",
        (1 if helpful else 0, datetime.utcnow(), log_id),
    )
    conn.commit()
    cursor.close()
    conn.close()


# ── Auth ─────────────────────────────────────────────────────────────────────
def get_user_by_username(username: str) -> Optional[Dict]:
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    return user


def create_user(username: str, password_hash: str, full_name: Optional[str] = None) -> int:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (username, password_hash, full_name) VALUES (%s, %s, %s)",
        (username, password_hash, full_name),
    )
    conn.commit()
    user_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return user_id

def delete_transaction(user_id: int, transaction_id: int) -> bool:
    """Hapus transaksi. user_id wajib disertakan supaya user tidak bisa hapus transaksi orang lain."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "DELETE FROM data_transaksi WHERE id = %s AND user_id = %s",
        (transaction_id, user_id)
    )
    conn.commit()
    affected = cursor.rowcount
    cursor.close()
    conn.close()
    return affected > 0


def get_recent_transactions(user_id: int, limit: int = 5) -> list:
    """Ambil transaksi terbaru untuk ditampilkan saat user mau hapus."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, tanggal, deskripsi, debit, kredit, jenis_akun, sub_kategori "
        "FROM data_transaksi WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, limit)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows