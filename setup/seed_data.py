"""
setup/seed_data.py
Script setup awal: baca CSV, buat embedding, upload ke Qdrant.
Jalankan SEKALI saat pertama kali setup sistem.

Usage:
  python setup/seed_data.py

Pastikan .env sudah diisi dan Qdrant + MySQL sudah berjalan.
"""

import csv
import os
import sys
import time

# Tambahkan root project ke path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.embedding_service import embed_batch, get_model
from app.services.qdrant_service import (
    ensure_collections,
    upsert_intent_sample,
    upsert_entity_sample,
    get_client,
)
from app.services.mysql_service import init_schema, get_connection
from app.config.settings import get_settings

settings = get_settings()

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def read_csv(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        # Handle semicolon separator
        sample = f.read(1024)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        return [
            {k.strip().strip('"'): v.strip().strip('"') for k, v in row.items()}
            for row in reader
        ]


def seed_intents():
    """Upload semua intent samples ke Qdrant: data_intent."""
    print("\n📥 Seeding intent samples...")
    rows = read_csv("intent_samples.csv")
    intent_map = {
        row["intent_id"]: row["intent_name"]
        for row in read_csv("intents.csv")
    }

    texts = [row["sample_text"] for row in rows]
    intents = [intent_map.get(row["intent_id"], "unknown") for row in rows]

    print(f"   Embedding {len(texts)} samples...")
    vectors = embed_batch(texts)

    for i, (text, intent, vector) in enumerate(zip(texts, intents, vectors)):
        upsert_intent_sample(vector, intent, text)
        if (i + 1) % 20 == 0:
            print(f"   {i+1}/{len(texts)} uploaded...")

    print(f"✅ {len(texts)} intent samples berhasil diupload ke Qdrant.")


def seed_entities():
    """Upload dict_user ke Qdrant: dict_user."""
    print("\n📥 Seeding entity dictionary...")
    rows = read_csv("dict_user.csv")

    # Embed keyword + sinonim sekaligus untuk coverage lebih luas
    all_texts = []
    all_meta = []

    for row in rows:
        keyword = row.get("keyword", "").strip()
        jenis = row.get("jenis_akun", "").strip()
        sub = row.get("sub_kategori", "").strip()
        sinonim_raw = row.get("sinonim", "")

        if not keyword:
            continue

        # Embed keyword utama
        all_texts.append(keyword)
        all_meta.append({"keyword": keyword, "jenis_akun": jenis, "sub_kategori": sub, "sinonim": sinonim_raw})

        # Embed setiap sinonim sebagai entitas terpisah (meningkatkan recall)
        import re
        sinonim_list = re.findall(r'"([^"]+)"', sinonim_raw)
        for s in sinonim_list:
            all_texts.append(s)
            all_meta.append({"keyword": s, "jenis_akun": jenis, "sub_kategori": sub, "sinonim": sinonim_raw})

    print(f"   Embedding {len(all_texts)} terms (keyword + sinonim)...")
    vectors = embed_batch(all_texts)

    for text, meta, vector in zip(all_texts, all_meta, vectors):
        upsert_entity_sample(
            vector=vector,
            keyword=meta["keyword"],
            jenis_akun=meta["jenis_akun"],
            sub_kategori=meta["sub_kategori"],
            sinonim=meta["sinonim"],
        )

    print(f"✅ {len(all_texts)} entity terms berhasil diupload ke Qdrant.")


def seed_mysql_reference_data():
    """Seed tabel intents, actions, intent_action_map, dict_user ke MySQL."""
    print("\n📥 Seeding MySQL reference tables...")
    conn = get_connection()
    cursor = conn.cursor()

    # Intents
    intents = read_csv("intents.csv")
    for row in intents:
        cursor.execute(
            "INSERT IGNORE INTO intents (intent_id, intent_name, description) VALUES (%s, %s, %s)",
            (row.get("intent_id"), row.get("intent_name"), row.get("description", "")),
        )

    # Actions
    actions = read_csv("actions.csv")
    for row in actions:
        cursor.execute(
            "INSERT IGNORE INTO actions (action_id, action_name) VALUES (%s, %s)",
            (row.get("action_id"), row.get("action_name")),
        )

    # Intent-Action Map
    maps = read_csv("intent_action_map.csv")
    for row in maps:
        cursor.execute(
            "INSERT IGNORE INTO intent_action_map (map_id, intent_id, action_id) VALUES (%s, %s, %s)",
            (row.get("map_id"), row.get("intent_id"), row.get("action_id")),
        )

    # Dict User
    dict_rows = read_csv("dict_user.csv")
    for row in dict_rows:
        cursor.execute(
            "INSERT IGNORE INTO dict_user (id, keyword, jenis_akun, sub_kategori, sinonim) VALUES (%s, %s, %s, %s, %s)",
            (row.get("id"), row.get("keyword"), row.get("jenis_akun"), row.get("sub_kategori"), row.get("sinonim", "")),
        )

    conn.commit()
    cursor.close()
    conn.close()
    print("✅ MySQL reference data berhasil di-seed.")


def main():
    print("=" * 50)
    print("  SETUP: Chatbot Keuangan")
    print("=" * 50)

    # 1. Pre-load model
    print("\n📦 Memuat embedding model...")
    get_model()

    # 2. Init MySQL schema
    print("\n🗄️  Inisialisasi MySQL schema...")
    init_schema()

    # 3. Pastikan Qdrant collections ada
    print("\n🔷 Inisialisasi Qdrant collections...")
    ensure_collections()

    # 4. Seed data
    seed_mysql_reference_data()
    seed_intents()
    seed_entities()

    print("\n" + "=" * 50)
    print("✅ Setup selesai! Sistem siap digunakan.")
    print("   Jalankan server dengan: python run.py")
    print("=" * 50)


if __name__ == "__main__":
    main()
