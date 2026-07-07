"""
setup/evaluate.py
Script evaluasi sistem untuk keperluan riset.
Menghitung: Accuracy, Macro-F1, Precision@1, MRR, Coverage, per-intent breakdown.

Dibaca dari tabel query_log di MySQL (data log runtime nyata),
atau dari CSV ground truth untuk offline evaluation.

Usage:
  # Evaluasi dari CSV ground truth
  python setup/evaluate.py --mode csv --csv data/test_intent.csv

  # Evaluasi dari query_log MySQL (data interaksi nyata)
  python setup/evaluate.py --mode db --from 2025-01-01 --to 2025-12-31
"""

import os
import sys
import csv
import argparse
from collections import defaultdict, Counter
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()


def evaluate_from_csv(csv_path: str, collection: str):
    """Jalankan prediksi pada CSV test set dan hitung metrik."""
    from app.services.embedding_service import embed_batch, get_model
    from app.services.qdrant_service import get_client
    from app.config.settings import get_settings
    settings = get_settings()

    samples = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            samples.append({"text": row["text"].strip(), "label": row["intent"].strip()})

    print(f"📂 {len(samples)} samples dari {csv_path}")

    get_model()
    texts = [s["text"] for s in samples]
    vectors = embed_batch(texts)
    client = get_client()

    predictions = []
    for sample, vector in zip(samples, vectors):
        hits = client.search(collection_name=collection, query_vector=vector, limit=5, with_payload=True)
        top_intent = hits[0].payload.get("intent_name", "unknown") if hits else "unknown"
        top_score  = hits[0].score if hits else 0.0
        threshold  = settings.threshold_intent

        predictions.append({
            "text":      sample["text"],
            "true":      sample["label"],
            "predicted": top_intent if top_score >= threshold else "unknown",
            "score":     top_score,
            "correct":   (top_intent == sample["label"]) and (top_score >= threshold),
            "hits":      [(h.payload.get("intent_name"), h.score) for h in hits],
        })

    return predictions


def evaluate_from_db(date_from: str, date_to: str):
    """Baca dari query_log. Butuh kolom user_feedback sebagai ground truth."""
    from app.services.mysql_service import get_connection
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT predicted_intent, intent_confidence, response_type, user_feedback
        FROM query_log
        WHERE request_ts BETWEEN %s AND %s
          AND predicted_intent IS NOT NULL
    """, (date_from, date_to))
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows


def compute_classification_metrics(predictions: list[dict]) -> dict:
    """Hitung Accuracy, Macro-F1, Weighted-F1, per-class breakdown."""
    classes = sorted(set(p["true"] for p in predictions))
    tp = defaultdict(int)
    fp = defaultdict(int)
    fn = defaultdict(int)

    for p in predictions:
        true  = p["true"]
        pred  = p["predicted"]
        if true == pred:
            tp[true] += 1
        else:
            fp[pred] += 1
            fn[true] += 1

    per_class = {}
    for cls in classes:
        prec = tp[cls] / (tp[cls] + fp[cls]) if (tp[cls] + fp[cls]) > 0 else 0.0
        rec  = tp[cls] / (tp[cls] + fn[cls]) if (tp[cls] + fn[cls]) > 0 else 0.0
        f1   = 2*prec*rec / (prec+rec) if (prec+rec) > 0 else 0.0
        support = sum(1 for p in predictions if p["true"] == cls)
        per_class[cls] = {"precision": prec, "recall": rec, "f1": f1, "support": support}

    total = len(predictions)
    correct = sum(1 for p in predictions if p["correct"])
    accuracy = correct / total if total > 0 else 0.0

    macro_f1    = sum(v["f1"] for v in per_class.values()) / len(per_class) if per_class else 0.0
    weighted_f1 = sum(v["f1"] * v["support"] for v in per_class.values()) / total if total > 0 else 0.0

    accepted = [p for p in predictions if p["score"] >= 0]
    coverage = len([p for p in predictions if p["predicted"] != "unknown"]) / total

    mrr = 0.0
    for p in predictions:
        for rank, (intent, score) in enumerate(p.get("hits", []), start=1):
            if intent == p["true"]:
                mrr += 1.0 / rank
                break
    mrr /= total if total > 0 else 1

    return {
        "total_samples": total,
        "accuracy": round(accuracy, 4),
        "macro_f1": round(macro_f1, 4),
        "weighted_f1": round(weighted_f1, 4),
        "mrr": round(mrr, 4),
        "coverage": round(coverage, 4),
        "per_class": per_class,
    }


def print_report(metrics: dict):
    print(f"\n{'='*60}")
    print(f"  LAPORAN EVALUASI")
    print(f"{'='*60}")
    print(f"  Total Samples  : {metrics['total_samples']}")
    print(f"  Accuracy       : {metrics['accuracy']:.4f}")
    print(f"  Macro-F1       : {metrics['macro_f1']:.4f}  ← METRIK UTAMA")
    print(f"  Weighted-F1    : {metrics['weighted_f1']:.4f}")
    print(f"  MRR            : {metrics['mrr']:.4f}")
    print(f"  Coverage       : {metrics['coverage']:.4f}")
    print(f"\n{'─'*60}")
    print(f"  {'Intent':<25} {'Prec':>8} {'Rec':>8} {'F1':>8} {'Support':>8}")
    print(f"{'─'*60}")
    for cls, m in sorted(metrics["per_class"].items()):
        print(f"  {cls:<25} {m['precision']:>8.4f} {m['recall']:>8.4f} {m['f1']:>8.4f} {m['support']:>8}")
    print(f"{'='*60}")
    print(f"\n  Gunakan tabel ini sebagai hasil eksperimen di paper.")
    print(f"  Laporkan: Macro-F1 sebagai metrik primer (bukan Accuracy).")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["csv", "db"], default="csv")
    parser.add_argument("--csv", default="data/test_intent.csv")
    parser.add_argument("--collection", default=None)
    parser.add_argument("--from", dest="date_from", default="2025-01-01")
    parser.add_argument("--to", dest="date_to", default=datetime.now().strftime("%Y-%m-%d"))
    args = parser.parse_args()

    from app.config.settings import get_settings
    settings = get_settings()

    if args.mode == "csv":
        collection = args.collection or settings.collection_intent
        if not os.path.exists(args.csv):
            print(f"❌ File tidak ditemukan: {args.csv}")
            print("   Format CSV: kolom 'text' dan 'intent'")
            sys.exit(1)
        predictions = evaluate_from_csv(args.csv, collection)
        metrics = compute_classification_metrics(predictions)
        print_report(metrics)

    elif args.mode == "db":
        print(f"📊 Membaca query_log dari {args.date_from} sampai {args.date_to}...")
        rows = evaluate_from_db(args.date_from, args.date_to)
        print(f"   {len(rows)} records ditemukan.")
        # Analisis sederhana dari DB (tanpa ground truth)
        dist = Counter(r["predicted_intent"] for r in rows)
        success = Counter(r["response_type"] for r in rows)
        print(f"\n  Distribusi Intent:")
        for k, v in dist.most_common():
            print(f"  • {k}: {v}")
        print(f"\n  Response Type:")
        for k, v in success.most_common():
            pct = v / len(rows) * 100
            print(f"  • {k}: {v} ({pct:.1f}%)")
        tcr = success.get("success", 0) / len(rows) if rows else 0
        print(f"\n  Task Completion Rate: {tcr:.4f}")


if __name__ == "__main__":
    main()
