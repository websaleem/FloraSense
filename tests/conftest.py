"""
Shared fixtures.

The suite deliberately never loads a real 100 MB checkpoint or a pretrained
torchvision backbone: that would make the tests slow enough that nobody runs
them, and would tie CI to model artefacts that are gitignored. Instead a tiny
stand-in model with the same interface the code depends on -- classifier,
class_to_idx, and a forward pass returning log-probabilities -- is written to
a real checkpoint file on disk, so the checkpoint resolution and loading paths
are exercised for real.
"""

import json

import pytest
import torch
from torch import nn

NUM_TEST_CLASSES = 4


class TinyModel(nn.Module):
    """Stands in for a torchvision backbone with a 4-class classifier head."""

    def __init__(self, num_classes=NUM_TEST_CLASSES):
        super().__init__()
        self.classifier = nn.Linear(3 * 224 * 224, num_classes)
        self.logsoftmax = nn.LogSoftmax(dim=1)

    def forward(self, x):
        return self.logsoftmax(self.classifier(x.flatten(1)))


@pytest.fixture
def device():
    return torch.device("cpu")


@pytest.fixture
def class_to_idx():
    return {str(i + 1): i for i in range(NUM_TEST_CLASSES)}


@pytest.fixture
def tiny_model(class_to_idx):
    model = TinyModel()
    model.class_to_idx = class_to_idx
    return model


@pytest.fixture
def flower_image(tmp_path):
    """A real JPEG on disk — process_image() opens files, not arrays."""
    from PIL import Image

    path = tmp_path / "flower.jpg"
    Image.new("RGB", (300, 400), color=(90, 140, 60)).save(path)
    return str(path)


@pytest.fixture
def cat_to_name_file(tmp_path, class_to_idx):
    path = tmp_path / "cat_to_name.json"
    names = {key: f"test flower {key}" for key in class_to_idx}
    path.write_text(json.dumps(names))
    return str(path)
