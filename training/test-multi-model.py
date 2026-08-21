# PROGRAMMER: Saleem Khan
# DATE CREATED: 3/11/2025
# Compares every supported architecture on a single image, side by side.

import argparse
import json
import os

import _paths  # noqa: F401  — puts backend/lambda on sys.path
import torch

from model_utils import SUPPORTED_ARCHITECTURES, load_checkpoint, predict


def get_input_args():
    """
        Parsing the arguments
    """
    parser = argparse.ArgumentParser(
        description=f'Predict a flower name with each trained model in {SUPPORTED_ARCHITECTURES}.')

    parser.add_argument('image_path', type=str, help='Path to test image flower.')
    parser.add_argument('--top_k', type=int, default=5, help='Returns top K predictions')
    parser.add_argument('--category_names', type=str,
                        default=os.path.join(_paths.BACKEND_DIR, 'cat_to_name.json'),
                        help='Path of JSON file having class name mapping.')
    parser.add_argument('--gpu', action='store_true', help='Use gpu if available')

    return parser.parse_args()


def report(arch, image_path, model, device, cat_to_name, top_k):
    """
        Run one model over the image and print its top-k table.
    """
    probs, classes = predict(image_path, model, device, top_k)
    flower_names = [cat_to_name[cls] for cls in classes]

    print("-" * 40)
    print(f"{'Class image':25s} : Probability using model '{arch}'")
    print("-" * 40)
    print(f"Most likely:\n{flower_names[0]:25s} : {probs[0]:.2f}")

    print("\nTop-K Results:")
    for name, prob in zip(flower_names, probs):
        print(f"{name:25s} : {prob:.2f}")
    print()


def main():
    """
        Load each architecture's checkpoint in turn and print its predictions
        for the same image, so the models can be compared directly.
    """
    args = get_input_args()

    # set the device based on gpu flag and availability of gpu
    device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")

    # load the category file mapping
    with open(args.category_names, 'r') as f:
        cat_to_name = json.load(f)

    for arch in SUPPORTED_ARCHITECTURES:
        # load_checkpoint returns None rather than raising when an architecture
        # has never been trained. Skipping keeps the comparison useful for the
        # models that do exist instead of aborting the whole run.
        model = load_checkpoint(arch, device, _paths.CHECKPOINT_DIR)
        if model is None:
            print(f"⚠  No checkpoint for '{arch}' — skipping. "
                  f"Train one with:  python training/train.py --arch {arch}\n")
            continue

        report(arch, args.image_path, model, device, cat_to_name, args.top_k)


if __name__ == '__main__':
    main()
