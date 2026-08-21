# PROGRAMMER: Saleem Khan
# DATE CREATED: 7/20/2026
# Shared model utilities for training, CLI prediction, and the web API.
# Centralises model loading, image processing, and inference logic.

import os
from typing import Optional

import torch
from torchvision import transforms, models
from torchvision.models import VGG16_Weights, DenseNet121_Weights, EfficientNet_B0_Weights
from PIL import Image


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SUPPORTED_ARCHITECTURES = ["vgg16", "densenet121", "efficientnet_b0"]

# ImageNet normalisation values used across training and inference
IMAGENET_MEAN = [0.485, 0.456, 0.406]
IMAGENET_STD = [0.229, 0.224, 0.225]


# ---------------------------------------------------------------------------
# Model construction
# ---------------------------------------------------------------------------
def build_model(arch: str):
    """
        Build and return a pre-trained torchvision model for the given
        architecture name.  Raises ValueError for unsupported architectures.
    """
    if arch == "vgg16":
        model = models.vgg16(weights=VGG16_Weights.DEFAULT)
        input_features = model.classifier[0].in_features
    elif arch == "densenet121":
        model = models.densenet121(weights=DenseNet121_Weights.DEFAULT)
        input_features = model.classifier.in_features
    elif arch == "efficientnet_b0":
        model = models.efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
        input_features = model.classifier[1].in_features
    else:
        raise ValueError(
            f"Unsupported architecture '{arch}'. "
            f"Choose from {SUPPORTED_ARCHITECTURES}"
        )
    return model, input_features


# ---------------------------------------------------------------------------
# Checkpoint resolution & loading
# ---------------------------------------------------------------------------
def resolve_checkpoint_path(arch: str, base_dir: str = ".") -> Optional[str]:
    """
        Find a checkpoint file for the given architecture.
        Search order: *_best.pth → *_latest.pth → legacy checkpoint_{arch}.pth.
        Returns the path if found, otherwise None.
    """
    candidates = [
        os.path.join(base_dir, f"checkpoint_{arch}_best.pth"),
        os.path.join(base_dir, f"checkpoint_{arch}_latest.pth"),
        os.path.join(base_dir, f"checkpoint_{arch}.pth"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def load_checkpoint(arch: str, device, base_dir: str = "."):
    """
        Build the base architecture, load a trained checkpoint, and
        return the model in eval mode.  Returns None if no checkpoint exists.
    """
    model, _ = build_model(arch)

    checkpoint_path = resolve_checkpoint_path(arch, base_dir)
    if checkpoint_path is None:
        return None

    checkpoint = torch.load(
        checkpoint_path, weights_only=False, map_location=device
    )
    model.classifier = checkpoint["classifier"]
    model.class_to_idx = checkpoint["class_to_idx"]
    model.load_state_dict(checkpoint["state_dict"])
    model.to(device)
    model.eval()
    return model


# ---------------------------------------------------------------------------
# Image processing
# ---------------------------------------------------------------------------
def process_image(image_path: str):
    """
        Scales, crops, and normalises a PIL image for a PyTorch model.
        Converts to RGB to handle PNG / RGBA inputs safely.
    """
    image = Image.open(image_path).convert("RGB")
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])
    return transform(image)


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
def predict(image_path: str, model, device, topk: int = 5):
    """
        Run inference on *image_path* and return (probabilities, class_keys).
    """
    model.eval()
    model.to(device)

    img = process_image(image_path).unsqueeze(0).to(device)

    with torch.no_grad():
        output = model(img)

    ps = torch.exp(output)
    top_p, top_class = ps.topk(topk, dim=1)

    idx_to_class = {idx: label for label, idx in model.class_to_idx.items()}
    top_classes = [idx_to_class[c.item()] for c in top_class[0]]

    return top_p[0].tolist(), top_classes
