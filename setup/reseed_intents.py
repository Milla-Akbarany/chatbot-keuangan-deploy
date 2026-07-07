"""
setup/reseed_intents.py
Script untuk re-seed intent samples ke Qdrant TANPA duplikat.

Digunakan ketika intent_samples.csv diperbarui.
Script ini akan:
1. Hapus koleksi data_intent yang lama
2. Buat ulang koleksi baru
3. Upload semua samples dari intent_samples.csv

Usage:
  python setup/reseed_intents.py
"""

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from app.services.embedding_service import embed_batch, get_model
from app.services.qdrant_service import get_client, upsert_intent_sample
from app.config.settings import get_settings
from qdrant_client.models import Distance, VectorParams

settings = get_settings()
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")


def read_csv(filename: str) -> list[dict]:
    path = os.path.join(DATA_DIR, filename)
    with open(path, encoding="utf-8") as f:
        sample = f.read(1024)
        f.seek(0)
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        return [
            {k.strip().strip('"'): (v.strip().strip('"') if v else "") for k, v in row.items()}
            for row in reader
            if any(v for v in row.values() if v)  # skip baris kosong
        ]

def reseed_intents():
    print("=" * 50)
    print("  RESEED: Intent Samples")
    print("=" * 50)

    # 1. Load model
    print("\n📦 Memuat embedding model...")
    get_model()

    # 2. Hapus koleksi lama dan buat ulang
    client = get_client()
    collection_name = settings.collection_intent

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
    print(f"   Koleksi '{collection_name}' berhasil dibuat.")

    # 3. Baca data
    print("\n📥 Membaca intent_samples.csv...")
    rows = read_csv("intent_samples.csv")
    intent_map = {
        row["intent_id"]: row["intent_name"]
        for row in read_csv("intents.csv")
    }

    texts = [row["sample_text"] for row in rows]
    intents = [intent_map.get(row["intent_id"], "unknown") for row in rows]

    print(f"   Total samples: {len(texts)}")

    # Tampilkan distribusi per intent
    from collections import Counter
    dist = Counter(intents)
    for intent, count in sorted(dist.items()):
        print(f"   - {intent}: {count} samples")

    # 4. Embed dan upload
    print(f"\n🔄 Embedding {len(texts)} samples...")
    vectors = embed_batch(texts)

    print(f"📤 Mengupload ke Qdrant...")
    for i, (text, intent, vector) in enumerate(zip(texts, intents, vectors)):
        upsert_intent_sample(vector, intent, text)
        if (i + 1) % 30 == 0:
            print(f"   {i+1}/{len(texts)} uploaded...")

    print(f"\n✅ {len(texts)} intent samples berhasil diupload ke Qdrant!")
    print("   Restart FastAPI agar perubahan berlaku: python run.py")
    print("=" * 50)


if __name__ == "__main__":
    reseed_intents()
