# Career Model — Evaluation Report

*Trained:* 2026-09-25T03:22:54+00:00  
*Dataset:* `data/resume_dataset.csv` — **synthetic** (3492 resumes, 22 roles)  
*Split:* train 2444 / validation 524 / test 524 (stratified, seed 42)  
*Features:* 281

> The model learns the patterns of a synthetic data generator. These metrics demonstrate the ML
> workflow; they are not claims about real-world hiring outcomes.

## Model comparison

| Model | Best params | Val macro-F1 | Test accuracy | Test precision (macro) | Test recall (macro) | Test macro-F1 | Test top-3 acc | Train time (s) |
|---|---|---|---|---|---|---|---|---|
| LogisticRegression **(selected)** | `{"C": 0.05}` | 0.9746 | 0.9866 | 0.9871 | 0.9867 | 0.9867 | 1.0000 | 0.1 |
| RandomForest | `{"n_estimators": 400, "max_depth": null, "min_samples_leaf": 1}` | 0.9624 | 0.9771 | 0.9781 | 0.9770 | 0.9770 | 1.0000 | 0.6 |
| XGBoost | `{"n_estimators": 350, "max_depth": 6, "learning_rate": 0.08}` | 0.9621 | 0.9752 | 0.9767 | 0.9748 | 0.9751 | 1.0000 | 4.7 |

Selected **LogisticRegression** by validation macro-F1.

## Per-class (selected model, test set)

| Role | Precision | Recall | F1 | Support |
|---|---|---|---|---|
| AI Engineer | 1.000 | 1.000 | 1.000 | 24 |
| Analytics Engineer | 1.000 | 0.958 | 0.979 | 24 |
| BI Developer | 1.000 | 1.000 | 1.000 | 25 |
| Backend Developer | 1.000 | 1.000 | 1.000 | 24 |
| Business Analyst | 1.000 | 1.000 | 1.000 | 26 |
| Cloud Engineer | 1.000 | 0.955 | 0.977 | 22 |
| Computer Vision Engineer | 1.000 | 1.000 | 1.000 | 24 |
| Cybersecurity Analyst | 0.955 | 0.913 | 0.933 | 23 |
| Data Analyst | 1.000 | 1.000 | 1.000 | 25 |
| Data Engineer | 0.960 | 1.000 | 0.980 | 24 |
| Data Scientist | 1.000 | 1.000 | 1.000 | 24 |
| Database Administrator | 1.000 | 1.000 | 1.000 | 25 |
| DevOps Engineer | 0.958 | 0.920 | 0.939 | 25 |
| Frontend Developer | 1.000 | 1.000 | 1.000 | 24 |
| Full Stack Developer | 1.000 | 1.000 | 1.000 | 25 |
| GenAI Engineer | 1.000 | 1.000 | 1.000 | 22 |
| ML Engineer | 1.000 | 1.000 | 1.000 | 22 |
| MLOps Engineer | 1.000 | 1.000 | 1.000 | 23 |
| NLP Engineer | 1.000 | 1.000 | 1.000 | 23 |
| Research Scientist | 1.000 | 1.000 | 1.000 | 22 |
| Security Engineer | 0.926 | 0.962 | 0.943 | 26 |
| Site Reliability Engineer | 0.917 | 1.000 | 0.957 | 22 |

## NLP pipeline vs. generator ground truth

* Skill extraction — precision 0.9993, recall 1.0, F1 0.9996
* Experience years MAE — 0.0
* Measured on synthetic resumes whose vocabulary comes from the same taxonomy; real resumes will score lower.

Confusion matrix: `models/confusion_matrix.csv`.
