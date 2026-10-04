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


# --------------------------------------------------------------------------
# Cold start
# --------------------------------------------------------------------------
class TestLambdaInitStaysCheap:
    """Lambda allows 10 seconds to initialise and loading the weights does not
    fit, so every cold start ended `Phase: init Status: timeout` and the
    request that caused it reached the browser as a 502. Under Lambda the load
    has to happen on the first request instead, where the 60-second function
    timeout applies."""

    def test_startup_under_lambda_does_not_load_the_model(
        self, monkeypatch, tiny_model, cat_to_name_file
    ):
        calls = []
        monkeypatch.setattr(
            lambda_handler, "load_checkpoint",
            lambda *a, **k: (calls.append(1), tiny_model)[1],
        )
        monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "florasense-api")

        with TestClient(lambda_handler.app):
            assert calls == [], "the model was loaded during the Lambda init phase"

    def test_the_first_request_loads_it(self, monkeypatch, tiny_model, cat_to_name_file):
        calls = []
        monkeypatch.setattr(
            lambda_handler, "load_checkpoint",
            lambda *a, **k: (calls.append(1), tiny_model)[1],
        )
        monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "florasense-api")

        with TestClient(lambda_handler.app) as c:
            # top_k=1: the stand-in model has far fewer than 102 classes, and
            # the default of 5 would overrun it. This test is about when the
            # load happens, not about what is predicted.
            resp = c.post(
                "/predict?top_k=1",
                files={"file": ("flower.jpg", image_bytes(), "image/jpeg")},
            )

        assert calls == [1], "the first request did not load the model exactly once"
        assert resp.status_code == 200

    def test_a_missing_checkpoint_is_not_retried_on_every_request(
        self, monkeypatch, cat_to_name_file
    ):
        """Searching for weights that are not there is not free, and a 503 does
        not become a 200 by asking again."""
        calls = []
        monkeypatch.setattr(
            lambda_handler, "load_checkpoint",
            lambda *a, **k: (calls.append(1), None)[1],
        )
        monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "florasense-api")

        with TestClient(lambda_handler.app) as c:
            for _ in range(3):
                resp = c.post(
                    "/predict", files={"file": ("flower.jpg", image_bytes(), "image/jpeg")}
                )
                assert resp.status_code == 503

        assert calls == [1], f"load retried {len(calls)} times"

    def test_the_model_survives_a_second_lifespan_run(
        self, monkeypatch, tiny_model, cat_to_name_file
    ):
        """Mangum runs the ASGI lifespan on every invocation, not once per
        container. A lifespan that resets the module globals therefore threw
        the loaded model away between requests: every prediction reloaded it
        (12.4s instead of 0.2s) and /health reported model_loaded=false for the
        life of the container."""
        calls = []
        monkeypatch.setattr(
            lambda_handler, "load_checkpoint",
            lambda *a, **k: (calls.append(1), tiny_model)[1],
        )
        monkeypatch.setattr(lambda_handler, "resolve_checkpoint_path", lambda *a, **k: None)
        monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "florasense-api")

        # First invocation: startup, then a request that loads the model.
        with TestClient(lambda_handler.app) as c:
            c.post("/predict?top_k=1", files={"file": ("f.jpg", image_bytes(), "image/jpeg")})
        assert calls == [1]

        # Second invocation against the same warm container.
        with TestClient(lambda_handler.app) as c:
            assert c.get("/health").json()["model_loaded"] is True, \
                "the lifespan discarded the model between invocations"
            c.post("/predict?top_k=1", files={"file": ("f.jpg", image_bytes(), "image/jpeg")})

        assert calls == [1], f"model was reloaded {len(calls)} times across invocations"
