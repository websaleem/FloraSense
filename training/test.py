# PROGRAMMER: Saleem Khan
# DATE CREATED: 3/11/2025
# Reports held-out test-set accuracy for every trained architecture.

import argparse

import _paths  # noqa: F401  — puts backend/lambda on sys.path
import torch
from torch.utils.data import DataLoader
from torchvision import datasets, transforms
from tqdm import tqdm

from model_utils import (
    IMAGENET_MEAN,
    IMAGENET_STD,
    SUPPORTED_ARCHITECTURES,
    load_checkpoint,
)


def get_input_args():
    """
        Parsing the arguments
    """
    parser = argparse.ArgumentParser(
        description=f'Report test-set accuracy for each trained model in {SUPPORTED_ARCHITECTURES}.')
    parser.add_argument('--data_dir', type=str, default=_paths.DATA_DIR,
                        help='Directory of the dataset (default: data/flowers)')
    parser.add_argument('--gpu', action='store_true', help='Use gpu if available')

    return parser.parse_args()


def build_test_loader(data_dir):
    """
        Build the held-out test loader. The transform matches the validation
        path in train.py and process_image() in model_utils -- resize, centre
        crop, ImageNet normalisation -- so accuracy here is comparable to the
        validation numbers printed during training.
    """
    test_transform = transforms.Compose([
        transforms.Resize(255),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])

    test_dataset = datasets.ImageFolder(f'{data_dir}/test', transform=test_transform)
    return DataLoader(test_dataset, batch_size=64)


def test_accuracy(model, device, dataloader, desc):
    """
        Count correct top-1 predictions over the whole test set.
    """
    model.eval()
    model.to(device)

    correct = 0
    total = 0

    with torch.no_grad():
        for image, label in tqdm(dataloader, desc=desc, leave=False):
            image, label = image.to(device), label.to(device)

            logps = model(image)
            ps = torch.exp(logps)

            top_p, top_class = ps.topk(1, dim=1)
            equals = top_class == label.view(*top_class.shape)

            correct += equals.sum().item()
            total += label.size(0)

    return correct, total


def main():
    """
        Evaluate every architecture that has a checkpoint and print a
        comparison table of test-set accuracies.
    """
    args = get_input_args()

    # set the device based on gpu flag and availability of gpu
    device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")

    # Built once and reused: decoding the test set for each architecture in turn
    # would repeat the same disk work three times over.
    dataloader = build_test_loader(args.data_dir)

    results = []
    for arch in SUPPORTED_ARCHITECTURES:
        # Skip rather than abort: an untrained architecture should not stop the
        # ones that were trained from being reported.
        model = load_checkpoint(arch, device, _paths.CHECKPOINT_DIR)
        if model is None:
            print(f"⚠  No checkpoint for '{arch}' — skipping. "
                  f"Train one with:  python training/train.py --arch {arch}")
            continue

        correct, total = test_accuracy(model, device, dataloader, desc=f'Testing {arch}')
        results.append((arch, 100 * correct / total, correct, total))

    if not results:
        print("No trained checkpoints found — nothing to evaluate.")
        return

    print("-" * 46)
    print(f"{'Model':20s} : {'Accuracy':>10s} : Correct")
    print("-" * 46)
    for arch, accuracy, correct, total in results:
        print(f"{arch:20s} : {accuracy:9.2f}% : {correct}/{total}")


if __name__ == '__main__':
    main()
