"""Inference: CandidateProfile -> ranked role probabilities + transparent match scores + explanations."""
from __future__ import annotations

import logging
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from backend.app.config import MODELS_DIR
from backend.app.knowledge import KnowledgeBase, get_kb
from backend.app.schemas import CandidateProfile, CareerPredictions, RolePrediction
from backend.app.services.matching import role_match

logger = logging.getLogger(__name__)

MODEL_PATH = MODELS_DIR / "career_model.joblib"
DISCLAIMER = (
    "Probabilities come from a classifier trained on SYNTHETIC resumes; they reflect how closely your profile "
    "resembles the synthetic examples of each role, not your real-world hiring odds. The match score is a "
    "transparent skill-overlap calculation against the role's requirement weights."
)


class ModelNotTrainedError(RuntimeError):
    pass


class CareerPredictor:
    def __init__(self, bundle: dict[str, Any], kb: KnowledgeBase) -> None:
        self.model = bundle["model"]
        self.model_name: str = bundle["model_name"]
        self.le = bundle["label_encoder"]
        self.fb = bundle["feature_builder"]
        self.trained_at: str | None = bundle.get("trained_at")
        self.test_metrics: dict = bundle.get("test_metrics", {})
        self.kb = kb
        self._lock = threading.Lock()

    @classmethod
    def load(cls, path: Path = MODEL_PATH) -> "CareerPredictor":
        if not path.exists():
            raise ModelNotTrainedError(f"Model file not found at {path}. Run: python -m backend.app.ml.train")
        bundle = joblib.load(path)
        logger.info("Loaded %s career model trained at %s", bundle["model_name"], bundle.get("trained_at"))
        return cls(bundle, get_kb())

    def _proba(self, X: np.ndarray) -> np.ndarray:
        with self._lock:  # sklearn/xgboost predict is not guaranteed thread-safe under n_jobs
            return self.model.predict_proba(X)

    def _occlusion(self, profile: CandidateProfile, skills: set[str], class_idx: list[int]) -> dict[int, list[dict]]:
        """Model-agnostic attribution: drop each present skill and measure the probability change."""
        skill_list = sorted(skills)
        if not skill_list:
            return {c: [] for c in class_idx}
        base = self.fb.transform_one(profile, skills)
        rows = [self.fb.transform_one(profile, skills - {s}) for s in skill_list]
        probs = self._proba(np.vstack([base, *rows]))
        out: dict[int, list[dict]] = {}
        for c in class_idx:
            deltas = [(skill_list[i], float(probs[0, c] - probs[i + 1, c])) for i in range(len(skill_list))]
            deltas = [d for d in deltas if d[1] > 0.001]
            deltas.sort(key=lambda d: -d[1])
            out[c] = [{"feature": s, "type": "skill", "probability_drop_if_removed": round(v, 4)} for s, v in deltas[:5]]
        return out

    def predict(self, profile: CandidateProfile, top_k: int = 8) -> CareerPredictions:
        skills = set(profile.all_skill_names)
        proba = self._proba(self.fb.transform_one(profile).reshape(1, -1))[0]
        order = np.argsort(-proba)[:top_k]
        attributions = self._occlusion(profile, skills, [int(i) for i in order[:5]])

        preds: list[RolePrediction] = []
        for rank, idx in enumerate(order, start=1):
            role_name = str(self.le.classes_[idx])
            role = self.kb.roles[role_name]
            match = role_match(role, skills, self.kb)
            top_feats = attributions.get(int(idx), [])
            preds.append(RolePrediction(
                rank=rank, role=role_name, category=role.category, probability=round(float(proba[idx]), 4),
                match=match, explanation=_explain(role_name, role.experience_level, float(proba[idx]), rank, match, top_feats, profile),
                top_features=top_feats,
            ))
        return CareerPredictions(
            model_name=self.model_name, model_trained_at=self.trained_at,
            model_test_macro_f1=self.test_metrics.get("f1_macro"), disclaimer=DISCLAIMER, predictions=preds,
        )


def _explain(role: str, level: str, p: float, rank: int, m, top_feats: list[dict], profile: CandidateProfile) -> list[str]:
    n_req = len(m.matched_required) + len(m.partial_required) + len(m.missing_required)
    lines = [f"Model probability {p:.1%} (rank #{rank} of all roles)."]
    lines.append(
        f"You fully cover {len(m.matched_required)} of {n_req} required skills "
        f"(weighted coverage {m.required_coverage:.0%})"
        + (f": {', '.join(m.matched_required[:6])}{'…' if len(m.matched_required) > 6 else ''}." if m.matched_required else ".")
    )
    if m.partial_required:
        lines.append(f"Partial credit via related/implied skills for: {', '.join(m.partial_required[:5])}.")
    if m.missing_required:
        lines.append(f"Missing required skills: {', '.join(m.missing_required[:5])}{'…' if len(m.missing_required) > 5 else ''}.")
    if m.matched_optional:
        lines.append(f"Bonus skills that fit this role: {', '.join(m.matched_optional[:5])}.")
    if top_feats:
        lines.append("Skills that most increased the model's probability for this role: "
                     + ", ".join(f["feature"] for f in top_feats[:4]) + ".")
    lines.append(f"Your extracted experience: {profile.total_experience_years:g} years; this role is typically {level}-level.")
    return lines


_predictor: CareerPredictor | None = None
_predictor_lock = threading.Lock()


def get_predictor() -> CareerPredictor:
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            _predictor = CareerPredictor.load()
        return _predictor


def predict_career(profile: CandidateProfile, top_k: int = 8) -> CareerPredictions:
    """Tool entrypoint."""
    return get_predictor().predict(profile, top_k=top_k)


@lru_cache
def load_evaluation_report() -> dict | None:
    import json

    path = MODELS_DIR / "evaluation_report.json"
    return json.loads(path.read_text()) if path.exists() else None
