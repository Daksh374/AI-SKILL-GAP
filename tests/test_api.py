import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.config import get_settings
from backend.app.main import app


@pytest.fixture(scope="module")
def client():
    get_settings.cache_clear()
    with TestClient(app) as c:
        yield c


@pytest.fixture
def headers():
    return {"X-Session-ID": str(uuid.uuid4())}


def upload(client, headers, data, name="resume.docx"):
    return client.post("/api/resumes", headers=headers, files={"file": (name, data, "application/octet-stream")})


def test_health(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok" and body["model_trained"] is True and body["tavily_configured"] is False


def test_roles_and_report(client):
    roles = client.get("/api/roles").json()
    assert len(roles) >= 20
    report = client.get("/api/model/report").json()
    assert report["selected_model"] in {"LogisticRegression", "RandomForest", "XGBoost"}
    assert report["synthetic_data"] is True


def test_full_flow(client, headers, resume_docx):
    r = upload(client, headers, resume_docx)
    assert r.status_code == 200, r.text
    body = r.json()
    rid = body["resume"]["id"]
    preds = body["careers"]["predictions"]
    assert preds[0]["role"] in {"Data Analyst", "Data Scientist"}
    assert abs(sum(p["probability"] for p in preds) - 1) < 0.2 and all(p["explanation"] for p in preds)

    gap = client.get(f"/api/resumes/{rid}/skill-gap", params={"role": "Data Scientist"}, headers=headers).json()
    assert gap["role"] == "Data Scientist" and 0 <= gap["readiness_score"] <= 1

    rm = client.post(f"/api/resumes/{rid}/roadmap", headers=headers,
                     json={"role": "Data Scientist", "hours_per_week": 10, "include_resources": True}).json()
    assert rm["stages"] and rm["resources_status"] == "not_configured"
    assert all(not st["youtube"] and not st["coursera"] for st in rm["stages"])

    upd = client.patch(f"/api/roadmaps/{rm['id']}/progress", headers=headers, json={"stage_index": 0, "completed": True}).json()
    assert upd["stages"][0]["completed"] is True

    dash = client.get(f"/api/resumes/{rid}/dashboard", params={"role": "Data Scientist"}, headers=headers).json()
    assert dash["progress"]["stages_completed"] == 1 and dash["skill_count"] > 5

    latest = client.get(f"/api/resumes/{rid}/roadmap", params={"role": "Data Scientist"}, headers=headers).json()
    assert latest["id"] == rm["id"] and latest["stages"][0]["completed"] is True


def test_market_without_key_reports_not_configured(client, headers):
    r = client.post("/api/market", headers=headers, json={"role": "Data Engineer"}).json()
    assert r["status"] == "not_configured" and r["observed_sources"] == [] and r["ai_interpretation"] == []


def test_session_isolation(client, headers, resume_pdf):
    rid = upload(client, headers, resume_pdf, "cv.pdf").json()["resume"]["id"]
    other = {"X-Session-ID": str(uuid.uuid4())}
    assert client.get(f"/api/resumes/{rid}", headers=other).status_code == 404
    assert client.get(f"/api/resumes/{rid}", headers=headers).status_code == 200
    assert [x["id"] for x in client.get("/api/resumes", headers=other).json()] == []


def test_upload_errors(client, headers):
    assert upload(client, headers, b"hello", "resume.txt").status_code == 422
    assert client.get("/api/resumes", headers={"X-Session-ID": "bad id!"}).status_code == 400
    assert client.post("/api/market", headers=headers, json={"role": "Astronaut"}).status_code == 400
