# PROGRAMMER: Saleem Khan
# DATE CREATED: 7/20/2026
***REMOVED*** — AI-Powered Flower Identification API using FastAPI
# Serves a web UI and prediction endpoint powered by pre-trained PyTorch models
# Deployed as an AWS Lambda container image via the Mangum adapter.

import os
import json
import tempfile
import shutil
from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from mangum import Mangum

from model_utils import load_checkpoint, resolve_checkpoint_path, predict


# ---------------------------------------------------------------------------
# Global state populated at startup
# ---------------------------------------------------------------------------
_model = None
_cat_to_name: dict = {}
_device = None
_arch: str = ""


# ---------------------------------------------------------------------------
# FastAPI lifespan — load model once at startup
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _model, _cat_to_name, _device, _arch

    _arch = os.environ.get("ARCH", "vgg16")
    _device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # Load category mapping
    cat_path = os.path.join(os.path.dirname(__file__), "cat_to_name.json")
    with open(cat_path, "r") as f:
        _cat_to_name = json.load(f)

    # Try to load the model checkpoint
    base_dir = os.path.dirname(__file__) or "."
    _model = load_checkpoint(_arch, _device, base_dir)
    if _model is None:
        print(f"⚠  No checkpoint found for '{_arch}'. "
              f"Train a model first:  python train.py flowers --arch {_arch}")
    else:
        cp = resolve_checkpoint_path(_arch, base_dir)
        print(f"✓  Model '{_arch}' loaded from {cp} on {_device}")

    yield  # application runs here

    # cleanup (nothing to do)


# ---------------------------------------------------------------------------
# App & routes
# ---------------------------------------------------------------------------
app = FastAPI(
    title="FloraSense",
    description="FloraSense — AI-powered flower species identification using deep learning.",
    lifespan=lifespan,
)

# Configure CORS securely from environment or default domains
allowed_origins_env = os.environ.get(
    "ALLOWED_ORIGINS",
    "https://florasense.websaleem.com,https://dev.florasense.websaleem.com,https://websaleem.com,http://localhost:8000"
)
allowed_origins = [o.strip() for o in allowed_origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials="*" not in allowed_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

# Serve static assets (CSS / JS / images if any)
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """Serve the main web UI."""
    html_path = os.path.join(static_dir, "index.html")
    with open(html_path, "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/health")
async def health():
    """Quick health-check endpoint."""
    return {
        "status": "ok",
        "model_loaded": _model is not None,
        "architecture": _arch,
        "device": str(_device),
    }


@app.post("/predict")
async def predict_flower(file: UploadFile = File(...), top_k: int = 5):
    """
        Accept an uploaded image, run inference, and return the top-k
        predictions with human-readable flower names and probabilities.
    """
    if _model is None:
        raise HTTPException(
            status_code=503,
            detail=(f"No trained model available for '{_arch}'. "
                    f"Run: python train.py flowers --arch {_arch}"),
        )

    # Validate content type
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Uploaded file must be an image.")

    # Save the upload directly to a temp file on disk (prevents memory exhaustion DoS)
    suffix = os.path.splitext(file.filename or "img.jpg")[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        probs, classes = predict(tmp_path, _model, _device, topk=top_k)
        results = []
        for prob, cls in zip(probs, classes):
            results.append({
                "class_id": cls,
                "flower_name": _cat_to_name.get(cls, f"Unknown ({cls})"),
                "probability": round(prob, 4),
            })
        return JSONResponse(content={"predictions": results})
    except Exception as e:
        print(f"Error during flower prediction inference: {e}")
        raise HTTPException(status_code=500, detail="An internal error occurred during image prediction.")
    finally:
        os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# AWS Lambda entry point (Mangum adapter)
# ---------------------------------------------------------------------------
handler = Mangum(app)
