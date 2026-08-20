"""
End-to-end tests for the FastAPI app.

These run against the real app object through TestClient, including the
lifespan handler, so model loading, routing and error handling are all
exercised. The heavyweight part -- loading a trained backbone -- is replaced by
a stand-in so the suite stays fast and needs no gitignored checkpoint.
"""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

import lambda_handler


@pytest.fixture
def client(monkeypatch, tiny_model, cat_to_name_file):
    """App with a stand-in model already loaded."""
    monkeypatch.setattr(lambda_handler, "load_checkpoint", lambda *a, **k: tiny_model)
    monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)

    with TestClient(lambda_handler.app) as c:
        # cat_to_name is populated by the lifespan from the real file; point it
        # at the fixture's classes so name lookup matches the stand-in model.
        import json

        lambda_handler._cat_to_name = json.loads(open(cat_to_name_file).read())
        yield c


@pytest.fixture
def unloaded_client(monkeypatch):
    """App that failed to find any checkpoint."""
    monkeypatch.setattr(lambda_handler, "load_checkpoint", lambda *a, **k: None)
    monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)

    with TestClient(lambda_handler.app) as c:
        yield c


def image_bytes(mode="RGB", size=(300, 300), fmt="JPEG"):
    buf = io.BytesIO()
    Image.new(mode, size, color=(120, 80, 40) if mode == "RGB" else 0).save(buf, format=fmt)
    buf.seek(0)
    return buf


# --------------------------------------------------------------------------
# Health & UI
# --------------------------------------------------------------------------
def test_health_reports_loaded_model(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["model_loaded"] is True
    assert body["device"] == "cpu"


def test_health_reports_missing_model(unloaded_client):
    assert unloaded_client.get("/health").json()["model_loaded"] is False


def test_index_serves_the_web_ui(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "FloraSense" in resp.text


# --------------------------------------------------------------------------
# Prediction
# --------------------------------------------------------------------------
def test_predict_returns_ranked_predictions(client):
    resp = client.post(
        "/predict?top_k=3",
        files={"file": ("flower.jpg", image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200

    predictions = resp.json()["predictions"]
    assert len(predictions) == 3
    assert [p["probability"] for p in predictions] == sorted(
        (p["probability"] for p in predictions), reverse=True
    )
    for p in predictions:
        assert set(p) == {"class_id", "flower_name", "probability"}


def test_predict_without_a_model_returns_503(unloaded_client):
    """Not a 500: the model is absent, which is a deployment state, not a bug."""
    resp = unloaded_client.post(
        "/predict", files={"file": ("flower.jpg", image_bytes(), "image/jpeg")}
    )
    assert resp.status_code == 503


def test_predict_rejects_non_image_uploads(client):
    resp = client.post("/predict", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


@pytest.mark.parametrize("top_k", [0, -1, 103, 1000])
def test_predict_rejects_out_of_range_top_k(client, top_k):
    """
    The model can return at most 102 classes. Unbounded, these values raised
    inside Tensor.topk and were reported as a 500 -- a client mistake dressed
    up as a server fault.
    """
    resp = client.post(
        f"/predict?top_k={top_k}",
        files={"file": ("flower.jpg", image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 422


@pytest.mark.parametrize("top_k", [1, 4])
def test_predict_accepts_in_range_top_k(client, top_k):
    resp = client.post(
        f"/predict?top_k={top_k}",
        files={"file": ("flower.jpg", image_bytes(), "image/jpeg")},
    )
    assert resp.status_code == 200
    assert len(resp.json()["predictions"]) == top_k


def test_predict_accepts_png_with_alpha(client):
    """Phone screenshots and PNG exports carry an alpha channel."""
    resp = client.post(
        "/predict?top_k=2",
        files={"file": ("flower.png", image_bytes(mode="RGBA", fmt="PNG"), "image/png")},
    )
    assert resp.status_code == 200


def test_predict_does_not_leak_internals_on_failure(client, monkeypatch):
    """
    The handler catches inference errors and returns a generic message. A raw
    exception string here would expose file paths and tensor shapes.
    """
    def boom(*args, **kwargs):
        raise RuntimeError("checkpoint lives at /var/task/model/secret.pth")

    monkeypatch.setattr(lambda_handler, "predict", boom)

    resp = client.post(
        "/predict", files={"file": ("flower.jpg", image_bytes(), "image/jpeg")}
    )
    assert resp.status_code == 500
    assert "secret.pth" not in resp.text
