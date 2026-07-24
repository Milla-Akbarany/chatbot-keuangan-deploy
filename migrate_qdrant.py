from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

# =========================
# QDRANT LOKAL
# =========================
local_client = QdrantClient(
    host="localhost",
    port=6335,
)

# =========================
# QDRANT CLOUD
# =========================
cloud_client = QdrantClient(
    url="https://be6b5e1a-220c-443b-9837-fcf277bf4f97.us-west-1-0.aws.cloud.qdrant.io",
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIiwic3ViamVjdCI6ImFwaS1rZXk6MmQ4MzhkZTMtOGQwNy00NTllLTlkNDMtYjE4MzFhMTc1NzI4In0.p2aY_3K6ZMqjCowV_FS81tFyAmp0S1HfkpOPlkd9qLE",
)

collections = [
    "data_intent",
    "dict_user",
    "data_finance",
]

for collection_name in collections:
    print(f"\nMemproses collection: {collection_name}")

    # Buat collection di Cloud jika belum ada
    local_info = local_client.get_collection(collection_name)

    try:
        cloud_client.get_collection(collection_name)
        print(f"Collection {collection_name} sudah ada di Cloud.")
    except Exception:
        print(f"Membuat collection {collection_name} di Cloud...")

        cloud_client.create_collection(
            collection_name=collection_name,
            vectors_config=local_info.config.params.vectors,
        )

    # Ambil semua points dari lokal
    points, next_page = local_client.scroll(
        collection_name=collection_name,
        limit=100,
        with_payload=True,
        with_vectors=True,
    )

    total = 0

    while points:
        converted_points = [
            PointStruct(
                id=p.id,
                vector=p.vector,
                payload=p.payload,
            )
            for p in points
        ]

        cloud_client.upsert(
            collection_name=collection_name,
            points=converted_points,
        )

        total += len(points)
        print(f"  {total} points berhasil dipindahkan.")

        if next_page is None:
            break

        points, next_page = local_client.scroll(
            collection_name=collection_name,
            limit=100,
            offset=next_page,
            with_payload=True,
            with_vectors=True,
        )

    print(f"✅ {collection_name}: {total} points selesai.")


print("\n🎉 Semua collection selesai dipindahkan!")