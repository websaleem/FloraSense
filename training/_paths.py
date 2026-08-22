"""
Makes the shared backend module importable from the training scripts, and
defines where models and data live.

model_utils.py is the single source of truth for architecture construction,
checkpoint resolution, preprocessing and inference. It ships inside the Lambda
image, so it lives under backend/lambda/ rather than here — but training, CLI
prediction and evaluation all need exactly the same logic, and a second copy is
how the two drift apart.

Importing this module puts backend/lambda/ on sys.path:

    import _paths  # noqa: F401
    from model_utils import load_checkpoint

Python always puts the running script's own directory on sys.path, so this
works whether a script is invoked as `python train.py` from inside training/ or
as `python training/train.py` from the repository root.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BACKEND_DIR = os.path.join(REPO_ROOT, "backend", "lambda")

# Trained weights. Kept out of the repo root so that nothing stray lands beside
# the handler in the container image, where Python would try to parse a *.pth
# as a path configuration file at interpreter start.
CHECKPOINT_DIR = os.path.join(REPO_ROOT, "checkpoints")

# Default dataset location: data/flowers/{train,valid,test}
DATA_DIR = os.path.join(REPO_ROOT, "data", "flowers")

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

os.makedirs(CHECKPOINT_DIR, exist_ok=True)
