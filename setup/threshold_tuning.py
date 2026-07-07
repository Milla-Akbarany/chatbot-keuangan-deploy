"""
setup/threshold_tuning.py
Script untuk menentukan threshold optimal secara empiris.
Jalankan setelah seed_data.py dan setelah dataset validation set siap.

Output:
- Tabel precision / recall / F1 / coverage per threshold
- Threshold optimal yang disarankan (maksimum F1)
- Plot curve (jika matplotlib tersedia)

Usage:
  python setup/threshold_tuning.py --collection data_intent --csv data/validation_intent.csv

Format CSV validation:
  text,intent
  "halo selamat pagi",greeting
  "berapa saldo bulan ini",tanya_saldo
  ...
"""

import os
import sys
import csv
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.services.embedding_service import embed_batch, get_model
from app.services.qdrant_service import get_client
from app.config.settings import get_settings

settings = get_settings()


def load_validation_csv(path: str) -> list[dict]:
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({"text": row["text"].strip(), "label": row["intent"].strip()})
    return rows


def run_predictions(collection: str, samples: list[dict]) -> list[dict]:
    """Embed semua samples dan dapatkan top-1 hasil Qdrant + score."""
    print(f"  Embedding {len(samples)} samples...")
    texts = [s["text"] for s in samples]
    vectors = embed_batch(texts)

    client = get_client()
    results = []

    for sample, vector in zip(samples, vectors):
        hits = client.search(
            collection_name=collection,
            query_vector=vector,
            limit=1,
            with_payload=True,
        )
        if hits:
            top = hits[0]
            predicted = top.payload.get("intent_name", "unknown")
            score = top.score
        else:
            predicted = "unknown"
            score = 0.0

        results.append({
            "text":      sample["text"],
            "true":      sample["label"],
            "predicted": predicted,
            "score":     score,
            "correct":   predicted == sample["label"],
        })

    return results


def sweep_threshold(results: list[dict], start=0.30, end=0.95, step=0.05) -> list[dict]:
    """Hitung metrik untuk setiap nilai threshold."""
    thresholds = np.arange(start, end + step/2, step)
    metrics = []
    total = len(results)

    for t in thresholds:
        t = round(float(t), 2)
        accepted = [r for r in results if r["score"] >= t]
        n_accepted = len(accepted)

        if n_accepted == 0:
            metrics.append({
                "threshold": t, "precision": 0.0, "recall": 0.0,
                "f1": 0.0, "coverage": 0.0, "n_accepted": 0,
            })
            continue

        n_correct = sum(1 for r in accepted if r["correct"])
        precision = n_correct / n_accepted
        recall    = n_correct / total
        coverage  = n_accepted / total
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        metrics.append({
            "threshold": t,
            "precision": round(precision, 4),
            "recall":    round(recall, 4),
            "f1":        round(f1, 4),
            "coverage":  round(coverage, 4),
            "n_accepted": n_accepted,
        })

    return metrics


def print_table(metrics: list[dict], optimal_t: float):
    print(f"\n{'Threshold':>10} {'Precision':>10} {'Recall':>8} {'F1':>8} {'Coverage':>10} {'N Accept':>10}")
    print("-" * 62)
    for m in metrics:
        marker = " ← OPTIMAL" if m["threshold"] == optimal_t else ""
        print(
            f"{m['threshold']:>10.2f} {m['precision']:>10.4f} {m['recall']:>8.4f} "
            f"{m['f1']:>8.4f} {m['coverage']:>10.4f} {m['n_accepted']:>10}{marker}"
        )


def try_plot(metrics: list[dict], output_path: str = "threshold_curve.png"):
    try:
        import matplotlib.pyplot as plt

        thresholds = [m["threshold"] for m in metrics]
        precisions = [m["precision"] for m in metrics]
        recalls    = [m["recall"] for m in metrics]
        f1s        = [m["f1"] for m in metrics]
        coverages  = [m["coverage"] for m in metrics]

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))

        ax1.plot(thresholds, precisions, label="Precision", marker="o")
        ax1.plot(thresholds, recalls, label="Recall", marker="s")
        ax1.plot(thresholds, f1s, label="F1", marker="^", linewidth=2)
        ax1.set_xlabel("Threshold")
        ax1.set_ylabel("Score")
        ax1.set_title("Precision / Recall / F1 vs Threshold")
        ax1.legend()
        ax1.grid(True, alpha=0.3)

        ax2.plot(thresholds, coverages, label="Coverage", marker="D", color="purple")
        ax2.set_xlabel("Threshold")
        ax2.set_ylabel("Coverage Rate")
        ax2.set_title("Coverage vs Threshold")
        ax2.legend()
        ax2.grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150)
        print(f"\n📊 Plot disimpan: {output_path}")
    except ImportError:
        print("\n[INFO] matplotlib tidak tersedia. Install dengan: pip install matplotlib")


def main():
    parser = argparse.ArgumentParser(description="Threshold tuning untuk intent/entity classifier")
    parser.add_argument("--collection", default=settings.collection_intent,
                        help="Nama koleksi Qdrant yang akan dievaluasi")
    parser.add_argument("--csv", default="data/validation_intent.csv",
                        help="Path ke CSV validation set (kolom: text, intent)")
    parser.add_argument("--plot", default="threshold_curve.png",
                        help="Path output untuk plot")
    args = parser.parse_args()

    print("=" * 62)
    print(f"  THRESHOLD TUNING — koleksi: {args.collection}")
    print("=" * 62)

    if not os.path.exists(args.csv):
        print(f"\n❌ File tidak ditemukan: {args.csv}")
        print("   Buat file CSV dengan format:")
        print("   text,intent")
        print("   \"halo selamat pagi\",greeting")
        print("   \"berapa saldo saya\",tanya_saldo")
        sys.exit(1)

    print(f"\n📂 Membaca validation set: {args.csv}")
    samples = load_validation_csv(args.csv)
    print(f"   {len(samples)} samples dimuat.")

    # Distribusi kelas
    from collections import Counter
    dist = Counter(s["label"] for s in samples)
    print("\n   Distribusi kelas:")
    for cls, count in sorted(dist.items()):
        print(f"   • {cls}: {count} samples")

    print("\n🔍 Menjalankan prediksi...")
    get_model()
    results = run_predictions(args.collection, samples)

    print("\n📊 Sweep threshold...")
    metrics = sweep_threshold(results)
    optimal = max(metrics, key=lambda m: m["f1"])
    optimal_t = optimal["threshold"]

    print_table(metrics, optimal_t)

    print(f"\n{'='*62}")
    print(f"  THRESHOLD OPTIMAL (maksimum F1): {optimal_t}")
    print(f"  Precision : {optimal['precision']:.4f}")
    print(f"  Recall    : {optimal['recall']:.4f}")
    print(f"  F1        : {optimal['f1']:.4f}")
    print(f"  Coverage  : {optimal['coverage']:.4f} ({optimal['n_accepted']}/{len(samples)} queries diterima)")
    print(f"{'='*62}")
    print(f"\n  → Update .env: THRESHOLD_INTENT={optimal_t}")

    try_plot(metrics, args.plot)


if __name__ == "__main__":
    main()
