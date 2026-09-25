"""Train, compare and persist the career-ranking model.

    python -m backend.app.ml.train

Steps
  1. Load data/resume_dataset.csv (synthetic) and run every resume_text through the SAME NLP
     pipeline used for uploaded resumes -> CandidateProfile -> feature vector.
  2. Stratified split 70 / 15 / 15 (train / validation / test).
  3. Small hyper-parameter grid per model family (Logistic Regression, Random Forest, XGBoost),
     selected on validation macro-F1.
  4. Best family (by validation macro-F1) is persisted; test metrics are reported for all three.
  5. Writes models/career_model.joblib, models/evaluation_report.{json,md},
     models/confusion_matrix.csv, and an NLP-pipeline evaluation against the dataset's ground truth.

The model learns the patterns of the synthetic generator. Metrics demonstrate a real ML workflow;
they are not evidence about real-world hiring outcomes.
"""
from __future__ import annotations

import argparse
import json
import logging
import time
import warnings
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    top_k_accuracy_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier

from backend.app.config import DATA_DIR, MODELS_DIR
from backend.app.knowledge import get_kb
from backend.app.ml.features import FeatureBuilder
from backend.app.nlp.profile import build_profile

logger = logging.getLogger("train")
# scipy/sklearn version-mismatch noise from the lbfgs solver; harmless
warnings.filterwarnings("ignore", message="Unknown solver options")

# Reference "today" used by the synthetic generator for "Present" end dates.
DATASET_REFERENCE_DATE = date(2026, 6, 30)
SEED = 42


def candidate_models(n_classes: int) -> dict[str, list[tuple[dict[str, Any], Any]]]:
    lr = [
        ({"C": c}, Pipeline([("scale", StandardScaler()),
                             ("clf", LogisticRegression(C=c, max_iter=4000, random_state=SEED))]))
        for c in (0.05, 0.3, 1.0)
    ]
    rf = [
        ({"n_estimators": 400, "max_depth": d, "min_samples_leaf": leaf},
         RandomForestClassifier(n_estimators=400, max_depth=d, min_samples_leaf=leaf, class_weight="balanced_subsample",
                                n_jobs=-1, random_state=SEED))
        for d, leaf in ((None, 1), (24, 2))
    ]
    xgb = [
        ({"n_estimators": 350, "max_depth": d, "learning_rate": 0.08},
         XGBClassifier(n_estimators=350, max_depth=d, learning_rate=0.08, subsample=0.9, colsample_bytree=0.6,
                       objective="multi:softprob", num_class=n_classes, tree_method="hist", eval_metric="mlogloss",
                       random_state=SEED, n_jobs=-1))
        for d in (4, 6)
    ]
    return {"LogisticRegression": lr, "RandomForest": rf, "XGBoost": xgb}


def metrics(y_true: np.ndarray, proba: np.ndarray, labels: list[int]) -> dict[str, float]:
    y_pred = proba.argmax(axis=1)
    return {
        "accuracy": round(float(accuracy_score(y_true, y_pred)), 4),
        "precision_macro": round(float(precision_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "recall_macro": round(float(recall_score(y_true, y_pred, average="macro", zero_division=0)), 4),
        "f1_macro": round(float(f1_score(y_true, y_pred, average="macro")), 4),
        "top3_accuracy": round(float(top_k_accuracy_score(y_true, proba, k=3, labels=labels)), 4),
    }


def evaluate_nlp(df: pd.DataFrame, profiles: list) -> dict[str, Any]:
    tp = fp = fn = 0
    abs_err = []
    for row, prof in zip(df.itertuples(index=False), profiles):
        gt = set(str(row.skills).split(";")) if isinstance(row.skills, str) else set()
        pred = set(prof.all_skill_names)
        tp += len(gt & pred)
        fp += len(pred - gt)
        fn += len(gt - pred)
        abs_err.append(abs(prof.total_experience_years - float(row.experience_years)))
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return {
        "skill_extraction_precision": round(p, 4),
        "skill_extraction_recall": round(r, 4),
        "skill_extraction_f1": round(2 * p * r / (p + r), 4) if p + r else 0.0,
        "experience_years_mae": round(float(np.mean(abs_err)), 3),
        "n_resumes": len(df),
        "note": "Measured on synthetic resumes whose vocabulary comes from the same taxonomy; real resumes will score lower.",
    }


def write_markdown(report: dict[str, Any], path: Path) -> None:
    lines = [
        "# Career Model — Evaluation Report",
        "",
        f"*Trained:* {report['trained_at']}  ",
        f"*Dataset:* `{report['dataset']}` — **synthetic** ({report['n_samples']} resumes, {report['n_classes']} roles)  ",
        f"*Split:* train {report['split']['train']} / validation {report['split']['validation']} / test {report['split']['test']} (stratified, seed {SEED})  ",
        f"*Features:* {report['n_features']}",
        "",
        "> The model learns the patterns of a synthetic data generator. These metrics demonstrate the ML",
        "> workflow; they are not claims about real-world hiring outcomes.",
        "",
        "## Model comparison",
        "",
        "| Model | Best params | Val macro-F1 | Test accuracy | Test precision (macro) | Test recall (macro) | Test macro-F1 | Test top-3 acc | Train time (s) |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, r in report["models"].items():
        t = r["test"]
        lines.append(
            f"| {name}{' **(selected)**' if name == report['selected_model'] else ''} | `{json.dumps(r['best_params'])}` | "
            f"{r['validation']['f1_macro']:.4f} | {t['accuracy']:.4f} | {t['precision_macro']:.4f} | {t['recall_macro']:.4f} | "
            f"{t['f1_macro']:.4f} | {t['top3_accuracy']:.4f} | {r['train_seconds']:.1f} |"
        )
    lines += ["", f"Selected **{report['selected_model']}** by validation macro-F1.", "", "## Per-class (selected model, test set)", "",
              "| Role | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
    for role, m in report["per_class"].items():
        lines.append(f"| {role} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1-score']:.3f} | {int(m['support'])} |")
    nlp = report["nlp_pipeline"]
    lines += ["", "## NLP pipeline vs. generator ground truth", "",
              f"* Skill extraction — precision {nlp['skill_extraction_precision']}, recall {nlp['skill_extraction_recall']}, F1 {nlp['skill_extraction_f1']}",
              f"* Experience years MAE — {nlp['experience_years_mae']}",
              f"* {nlp['note']}", "", "Confusion matrix: `models/confusion_matrix.csv`.", ""]
    path.write_text("\n".join(lines))


def main() -> None:
    ap = argparse.ArgumentParser(description="Train the career-ranking model on data/resume_dataset.csv")
    ap.add_argument("--data", type=Path, default=DATA_DIR / "resume_dataset.csv")
    ap.add_argument("--out", type=Path, default=MODELS_DIR)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    kb = get_kb()
    df = pd.read_csv(args.data)
    df = df[df["target_role"].isin(kb.roles)].reset_index(drop=True)
    logger.info("Loaded %d synthetic resumes across %d roles", len(df), df["target_role"].nunique())

    t0 = time.time()
    profiles = [build_profile(t, use_ner=False, today=DATASET_REFERENCE_DATE) for t in df["resume_text"]]
    logger.info("NLP pipeline processed %d resumes in %.1fs", len(profiles), time.time() - t0)

    fb = FeatureBuilder.from_kb(kb)
    X = fb.transform(profiles)
    le = LabelEncoder().fit(sorted(kb.roles))
    y = le.transform(df["target_role"])
    labels = list(range(len(le.classes_)))

    idx = np.arange(len(df))
    idx_train, idx_tmp = train_test_split(idx, test_size=0.30, stratify=y, random_state=SEED)
    idx_val, idx_test = train_test_split(idx_tmp, test_size=0.50, stratify=y[idx_tmp], random_state=SEED)
    Xtr, Xva, Xte = X[idx_train], X[idx_val], X[idx_test]
    ytr, yva, yte = y[idx_train], y[idx_val], y[idx_test]
    logger.info("Split: train=%d val=%d test=%d, features=%d", len(ytr), len(yva), len(yte), X.shape[1])

    results: dict[str, Any] = {}
    fitted: dict[str, Any] = {}
    for family, grid in candidate_models(len(labels)).items():
        best = None
        for params, model in grid:
            ts = time.time()
            model.fit(Xtr, ytr)
            val = metrics(yva, model.predict_proba(Xva), labels)
            elapsed = time.time() - ts
            logger.info("%-18s %-60s val macro-F1=%.4f (%.1fs)", family, json.dumps(params), val["f1_macro"], elapsed)
            if best is None or val["f1_macro"] > best[1]["f1_macro"]:
                best = (params, val, model, elapsed)
        params, val, model, elapsed = best
        test_proba = model.predict_proba(Xte)
        results[family] = {"best_params": params, "validation": val, "test": metrics(yte, test_proba, labels),
                           "train_seconds": round(elapsed, 2)}
        fitted[family] = model

    selected = max(results, key=lambda k: results[k]["validation"]["f1_macro"])
    model = fitted[selected]
    y_pred = model.predict_proba(Xte).argmax(axis=1)
    cm = confusion_matrix(yte, y_pred, labels=labels)
    per_class = classification_report(yte, y_pred, labels=labels, target_names=list(le.classes_), output_dict=True, zero_division=0)
    per_class = {k: v for k, v in per_class.items() if k in le.classes_}

    args.out.mkdir(parents=True, exist_ok=True)
    trained_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    report = {
        "trained_at": trained_at,
        "dataset": str(args.data.relative_to(args.data.parents[1])) if args.data.is_relative_to(args.data.parents[1]) else str(args.data),
        "synthetic_data": True,
        "n_samples": int(len(df)),
        "n_classes": len(labels),
        "n_features": int(X.shape[1]),
        "split": {"train": int(len(ytr)), "validation": int(len(yva)), "test": int(len(yte))},
        "selection_metric": "validation macro-F1",
        "selected_model": selected,
        "models": results,
        "per_class": per_class,
        "nlp_pipeline": evaluate_nlp(df, profiles),
    }
    (args.out / "evaluation_report.json").write_text(json.dumps(report, indent=2))
    write_markdown(report, args.out / "evaluation_report.md")
    pd.DataFrame(cm, index=le.classes_, columns=le.classes_).to_csv(args.out / "confusion_matrix.csv")
    joblib.dump(
        {
            "model": model,
            "model_name": selected,
            "label_encoder": le,
            "feature_builder": fb,
            "feature_names": fb.feature_names,
            "trained_at": trained_at,
            "test_metrics": results[selected]["test"],
            "reference_date": DATASET_REFERENCE_DATE.isoformat(),
        },
        args.out / "career_model.joblib",
    )

    print("\n=== Model comparison (test set) ===")
    print(f"{'model':<20}{'val F1':>8}{'acc':>8}{'prec':>8}{'rec':>8}{'F1':>8}{'top3':>8}")
    for name, r in results.items():
        t = r["test"]
        mark = " <- selected" if name == selected else ""
        print(f"{name:<20}{r['validation']['f1_macro']:>8.4f}{t['accuracy']:>8.4f}{t['precision_macro']:>8.4f}"
              f"{t['recall_macro']:>8.4f}{t['f1_macro']:>8.4f}{t['top3_accuracy']:>8.4f}{mark}")
    print(f"\nNLP pipeline: {report['nlp_pipeline']}")
    print(f"Saved model to {args.out / 'career_model.joblib'} and report to {args.out / 'evaluation_report.md'}")


if __name__ == "__main__":
    main()
