# PROGRAMMER: Saleem Khan
# DATE CREATED: 3/11/2025    
# Prediction application using model vgg16 or densenet121 or efficientnet_b0

import argparse
import torch
from torchvision import transforms, models
from torchvision.models import VGG16_Weights, DenseNet121_Weights, EfficientNet_B0_Weights
from PIL import Image
import json
import time

def get_input_args():
    """
        Parsing the arguments
    """    
    parser = argparse.ArgumentParser(description='Predict flower name using a trained model.')

    parser.add_argument('image_path', type=str, help='Path to test image flower.')
    parser.add_argument('--arch', type=str, default='vgg16', help='Choose the model acrchitecture from ["vgg16", "densenet121", "efficientnet_b0"]')
    parser.add_argument('--top_k', type=int, default=5, help='Returns top K predictions')
    parser.add_argument('--category_names', type=str, default='cat_to_name.json', help='Path of JSON file having class name mapping.')
    parser.add_argument('--gpu', action='store_true', help='Use gpu if available')
    
    return parser.parse_args()


# This function loads a checkpoint and rebuilds the model
def load_checkpoint(args, device):
    """
        Load the model from the checkpoint file
    """
    # first get model based on the architecture
    if args.arch == 'vgg16':
        model = models.vgg16(weights=VGG16_Weights.DEFAULT)
    elif args.arch == 'densenet121':
        model = models.densenet121(weights=DenseNet121_Weights.DEFAULT)
    elif args.arch == 'efficientnet_b0':
        model = models.efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
    else:
        print(f"Unsupported {args.arch} architecture model argument, use default model 'vgg16'")
        args.arch = 'vgg16'
        model = models.vgg16(weights=VGG16_Weights.DEFAULT)

    checkpoint_file = f'./checkpoint_{args.arch}.pth'
    
    # load the checkpoint file
    checkpoint = torch.load(checkpoint_file, weights_only=False, map_location=torch.device(device))
        
    model.classifier = checkpoint['classifier']
    model.class_to_idx = checkpoint['class_to_idx']
    model.load_state_dict(checkpoint['state_dict'])
    
    return model


def process_image(image_path):
    """ Scales, crops, and normalizes a PIL image for a PyTorch model,
        returns an Numpy array
    """
    # Done: Process a PIL image for use in a PyTorch model
    image = Image.open(image_path)
    
    transform = transforms.Compose([
        transforms.Resize(256),
        transforms.CenterCrop(224),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406],
                             [0.229, 0.224, 0.225])
    ])
    
    return transform(image)

def predict(image_path, model, device, topk=5):
    """
        Predict the class (or classes) of an image using 
        a trained deep learning model.
    """
    
    # set model to evaluation mode
    model.eval()
    
    # load to the appropriate device
    model.to(device)
    
    # pre process the test image
    img = process_image(image_path).unsqueeze(0).to(device)
    
    # pass to the model with no gradient
    with torch.no_grad():
        output = model(img)

    # get the probablity of output
    ps = torch.exp(output)
    
    # find the top probablity and classes
    top_p, top_class = ps.topk(topk, dim=1)
    
    # map the idx to corresponding class labels
    idx_to_class = {index: label for label, index in model.class_to_idx.items()}
    
    # get the top classes names
    top_classes = [idx_to_class[cls.item()] for cls in top_class[0]]
    
    return top_p[0].tolist(), top_classes



def main():
    """
        This function parse the arguments and load checkpoints
        and finally call the predict method to get the predictions
    """
    args = get_input_args()
    print(args)
    # set the device based on gpu flag and availability of gpu
    device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")
            
    # load the checkpoint
    model = load_checkpoint(args, device)

    # load the category file mapping
    with open(args.category_names, 'r') as f:
        cat_to_name = json.load(f)

    # start time for prediction
    start_time = time.time()
    
    # predict the flower name
    probs, classes = predict(args.image_path, model, device, args.top_k)

    # end time for prediction
    end_time = time.time()

    # calculate time taken to predict
    predict_time = end_time - start_time
    
    # use the category class file to fine names
    flower_names = [cat_to_name[cls] for cls in classes]
    
    print("-" * 40)
    print(f"{'Class image':25s} : Probabilty")
    print("-" * 40)
    print(f"Most likely:\n{flower_names[0]:25s} : {probs[0]:.2f}")
    
    print(f"\nTop-K Results:")
    for i in range(len(flower_names)):
        print(f"{flower_names[i]:25s} : {probs[i]:.2f}")

if __name__ == '__main__':
    main()
