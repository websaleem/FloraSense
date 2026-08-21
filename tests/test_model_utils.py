"""Unit tests for the shared model utilities."""

import os

import pytest
import torch
from PIL import Image

from model_utils import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    SUPPORTED_ARCHITECTURES,
    build_model,
    load_checkpoint,
    predict,
    process_image,
    resolve_checkpoint_path,
)


# --------------------------------------------------------------------------
# Checkpoint resolution
# --------------------------------------------------------------------------
def _write(path):
    torch.save({"marker": True}, path)


def test_resolve_returns_none_when_nothing_exists(tmp_path):
    assert resolve_checkpoint_path("vgg16", str(tmp_path)) is None


def test_resolve_prefers_best_then_latest_then_legacy(tmp_path):
    """
    Priority order is a contract, not a detail: deploy.sh mirrors it to decide
    which checkpoint gets baked into the image. If the two ever disagree, the
    deployed model stops matching the one evaluated locally.
    """
    legacy = tmp_path / "checkpoint_vgg16.pth"
    latest = tmp_path / "checkpoint_vgg16_latest.pth"
    best = tmp_path / "checkpoint_vgg16_best.pth"

    _write(legacy)
    assert resolve_checkpoint_path("vgg16", str(tmp_path)) == str(legacy)

    _write(latest)
    assert resolve_checkpoint_path("vgg16", str(tmp_path)) == str(latest)

    _write(best)
    assert resolve_checkpoint_path("vgg16", str(tmp_path)) == str(best)


def test_resolve_is_architecture_scoped(tmp_path):
    _write(tmp_path / "checkpoint_vgg16_best.pth")
    assert resolve_checkpoint_path("densenet121", str(tmp_path)) is None


# --------------------------------------------------------------------------
# Checkpoint loading
# --------------------------------------------------------------------------
def test_load_checkpoint_returns_none_when_missing(tmp_path, device):
    """
    A missing checkpoint must not raise: lambda_handler relies on None to serve
    a 503 with an actionable message instead of failing the whole cold start.
    """
    assert load_checkpoint("efficientnet_b0", device, str(tmp_path)) is None


def test_load_checkpoint_restores_classifier_and_classes(tmp_path, device, tiny_model, class_to_idx):
    torch.save(
        {
            "architecture": "tiny",
            "classifier": tiny_model.classifier,
            "class_to_idx": class_to_idx,
            "state_dict": tiny_model.state_dict(),
        },
        tmp_path / "checkpoint_tiny_best.pth",
    )

    import model_utils

    # build_model() only knows real torchvision architectures, so swap in the
    # stand-in to test the loading logic itself rather than torchvision.
    original = model_utils.build_model
    model_utils.build_model = lambda arch: (type(tiny_model)(), None)
    try:
        model = load_checkpoint("tiny", device, str(tmp_path))
    finally:
        model_utils.build_model = original

    assert model is not None
    assert model.class_to_idx == class_to_idx
    assert not model.training, "model must be returned in eval mode"


# --------------------------------------------------------------------------
# Architecture construction
# --------------------------------------------------------------------------
def test_build_model_rejects_unknown_architecture():
    with pytest.raises(ValueError) as exc:
        build_model("resnet50")
    assert "resnet50" in str(exc.value)


def test_supported_architectures_are_the_documented_three():
    assert SUPPORTED_ARCHITECTURES == ["vgg16", "densenet121", "efficientnet_b0"]


# --------------------------------------------------------------------------
# Image processing
# --------------------------------------------------------------------------
def test_process_image_shape(flower_image):
    assert process_image(flower_image).shape == (3, 224, 224)


def test_process_image_applies_imagenet_normalisation(tmp_path):
    """
    Written as a lossless PNG on purpose: a solid colour survives resize and
    crop exactly, so the expected value can be asserted tightly. The same
    picture saved as JPEG comes back off by a quantisation level and forces a
    tolerance loose enough to hide a genuinely wrong mean or std.
    """
    colour = (90, 140, 60)
    path = tmp_path / "solid.png"
    Image.new("RGB", (300, 400), color=colour).save(path)

    tensor = process_image(str(path))

    for channel, (mean, std) in enumerate(zip(IMAGENET_MEAN, IMAGENET_STD)):
        raw = colour[channel] / 255
        assert tensor[channel].mean().item() == pytest.approx((raw - mean) / std, abs=1e-4)


@pytest.mark.parametrize("mode", ["RGBA", "L", "P"])
def test_process_image_converts_non_rgb_inputs(tmp_path, mode):
    """
    Users upload PNGs with alpha and greyscale scans. Without the RGB
    conversion these reach the first conv layer with the wrong channel count
    and raise, which surfaces as a 500 on a perfectly valid photo.
    """
    path = tmp_path / f"flower_{mode}.png"
    Image.new(mode, (300, 300)).save(path)

    assert process_image(str(path)).shape == (3, 224, 224)


# --------------------------------------------------------------------------
# Inference
# --------------------------------------------------------------------------
def test_predict_returns_sorted_probabilities_and_class_keys(flower_image, tiny_model, device):
    probs, classes = predict(flower_image, tiny_model, device, topk=3)

    assert len(probs) == len(classes) == 3
    assert probs == sorted(probs, reverse=True)
    assert all(cls in tiny_model.class_to_idx for cls in classes)
    assert all(0.0 <= p <= 1.0 for p in probs)


def test_predict_maps_indices_back_to_original_class_keys(flower_image, tiny_model, device):
    """
    ImageFolder sorts classes as strings, so index 1 is class "2", not "1".
    An off-by-one here silently mislabels every prediction.
    """
    _, classes = predict(flower_image, tiny_model, device, topk=4)
    assert sorted(classes) == sorted(tiny_model.class_to_idx.keys())
