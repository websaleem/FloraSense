# PROGRAMMER: Saleem Khan
# DATE CREATED: 3/11/2025
# CLI prediction application using model vgg16 or densenet121 or efficientnet_b0

import argparse
import json
import torch

from model_utils import (
    SUPPORTED_ARCHITECTURES,
    load_checkpoint,
    predict,
)


def get_input_args():
    """
        Parsing the arguments
    """
    parser = argparse.ArgumentParser(description='Predict flower name using a trained model.')

    parser.add_argument('image_path', type=str, help='Path to test image flower.')
    parser.add_argument('--arch', type=str, default='vgg16',
                        help=f'Choose the model architecture from {SUPPORTED_ARCHITECTURES}')
    parser.add_argument('--top_k', type=int, default=5, help='Returns top K predictions')
    parser.add_argument('--category_names', type=str, default='cat_to_name.json',
                        help='Path of JSON file having class name mapping.')
    parser.add_argument('--gpu', action='store_true', help='Use gpu if available')

    return parser.parse_args()


def main():
    """
        This function parse the arguments and load checkpoints
        and finally call the predict method to get the predictions
    """
    args = get_input_args()
    print(args)

    # set the device based on gpu flag and availability of gpu
    device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")

    # load the checkpoint using shared utility
    model = load_checkpoint(args.arch, device)
    if model is None:
        print(f"Error: No checkpoint found for '{args.arch}'. "
              f"Train a model first: python train.py flowers --arch {args.arch}")
        return

    # load the category file mapping
    with open(args.category_names, 'r') as f:
        cat_to_name = json.load(f)

    # predict the flower name using shared utility
    probs, classes = predict(args.image_path, model, device, args.top_k)

    # use the category class file to find names
    flower_names = [cat_to_name[cls] for cls in classes]

    print("-" * 40)
    print(f"{'Class image':25s} : Probability")
    print("-" * 40)
    print(f"Most likely:\n{flower_names[0]:25s} : {probs[0]:.2f}")

    print(f"\nTop-K Results:")
    for i in range(len(flower_names)):
        print(f"{flower_names[i]:25s} : {probs[i]:.2f}")


if __name__ == '__main__':
    main()
