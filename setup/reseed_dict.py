"""
setup/reseed_dict.py
Script untuk re-seed dict_user ke Qdrant TANPA duplikat.

Digunakan ketika dict_user.csv diperbarui.
Script ini akan:
1. Hapus koleksi dict_user yang lama
2. Buat ulang koleksi baru
3. Upload semua data dari dict_user.csv

Usage:
  python setup/reseed_dict.py
"""

import csv
import os
import sys
import ast

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.embedding_service import embed_batch, get_model
from app.services.qdrant_service import get_client
from app.config.settings import get_settings
from qdrant_client.models import Distance, VectorParams, PointStruct
import uuid

settings = get_settings()
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def read_dict_user():
    path = os.path.join(DATA_DIR, "dict_user.csv")
    rows = []
    with open(path, encoding="utf-8") as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            rows.append({
                k.strip().strip('"'): (v.strip().strip('"') if v else "")
                for k, v in row.items()
                if k
            })
    return rows


def parse_sinonim(sinonim_str: str) -> list:
    """Parse sinonim dari string list Python."""
    try:
        return ast.literal_eval(sinonim_str)
    except Exception:
        return [sinonim_str] if sinonim_str else []


def reseed_dict():
    print("=" * 50)
    print("  RESEED: Dict User (Kamus Entitas)")
    print("=" * 50)

    # 1. Load model
    print("\n📦 Memuat embedding model...")
    get_model()

    # 2. Hapus dan buat ulang koleksi
    client = get_client()
    collection_name = settings.collection_entity  # "dict_user"

    print(f"\n🗑️  Menghapus koleksi lama '{collection_name}'...")
    try:
        client.delete_collection(collection_name)
        print(f"   Koleksi '{collection_name}' berhasil dihapus.")
    except Exception as e:
        print(f"   Koleksi tidak ada atau gagal dihapus: {e}")

    print(f"\n🔷 Membuat koleksi baru '{collection_name}'...")
    client.create_collection(
        collection_name=collection_name,
        vectors_config=VectorParams(
            size=settings.embedding_dim,
            distance=Distance.COSINE,
        ),
    )

    # 3. Baca dan proses data
    print("\n📥 Membaca dict_user.csv...")
    rows = read_dict_user()
    print(f"   Total entitas: {len(rows)}")

    texts = []
    payloads = []

    for row in rows:
        keyword = row.get("keyword", "")
        jenis_akun = row.get("jenis_akun", "")
        sub_kategori = row.get("sub_kategori", "")
        sinonim_raw = row.get("sinonim", "[]")
        sinonim_list = parse_sinonim(sinonim_raw)

        # Teks utama
        texts.append(keyword)
        payloads.append({
            "keyword": keyword,
            "jenis_akun": jenis_akun,
            "sub_kategori": sub_kategori,
        })

        # Tambahkan sinonim sebagai entry terpisah
        for s in sinonim_list:
            if s.strip():
                texts.append(s.strip())
                payloads.append({
                    "keyword": s.strip(),
                    "jenis_akun": jenis_akun,
                    "sub_kategori": sub_kategori,
                })

    print(f"   Total vectors (keyword + sinonim): {len(texts)}")

    # 4. Embed dan upload
    print(f"\n🔄 Embedding {len(texts)} texts...")
    vectors = embed_batch(texts)

    print(f"📤 Mengupload ke Qdrant...")
    points = []
    for text, payload, vector in zip(texts, payloads, vectors):
        points.append(PointStruct(
            id=str(uuid.uuid4()),
            vector=vector,
            payload=payload,
        ))

    # Upload batch
    batch_size = 50
    for i in range(0, len(points), batch_size):
        batch = points[i:i + batch_size]
        client.upsert(collection_name=collection_name, points=batch)
        print(f"   {min(i + batch_size, len(points))}/{len(points)} uploaded...")

    print(f"\n✅ {len(points)} vectors berhasil diupload ke Qdrant!")
    print("   Tampilkan mapping yang diupload:")
    for row in rows:
        print(f"   - {(row.get('keyword') or ''):20s} → {(row.get('jenis_akun') or ''):12s} → {row.get('sub_kategori') or ''}")
    print("\n   Restart FastAPI agar perubahan berlaku: python run.py")
    print("=" * 50)


if __name__ == "__main__":
    reseed_dict()
