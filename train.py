# PROGRAMMER: Saleem Khan
# DATE CREATED: 3/11/2025    
# Training module using model vgg16 or densenet121 or efficientnet_b0

import argparse
import torch
from torch import nn, optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, models
from torchvision.models import VGG16_Weights, DenseNet121_Weights, EfficientNet_B0_Weights
from tqdm import tqdm
import os
from datetime import datetime


def get_input_args():
    """
        Parsing the arguments
    """      
    parser = argparse.ArgumentParser(description='Tranining an Image Classifier.')
    
    parser.add_argument('data_dir', type=str, default='flowers', help='Directory of the dataset (i.e. flowers)')
    parser.add_argument('--arch', type=str, default='vgg16', help='Choose the model acrchitecture from ["vgg16", "densenet121", "efficientnet_b0"]')
    parser.add_argument('--learning_rate', type=float, default=0.001, help='Learning rate')
    parser.add_argument('--hidden_layers', type=int, default=4096, help='Number of hidden layers')
    parser.add_argument('--epochs', type=int, default=5, help='epochs to run')
    parser.add_argument('--gpu', action='store_true', help='Use gpu if available')
    
    return parser.parse_args()

# Save the checkpoint 
def save_checkpoint(model, class_to_idx):
    """
        Save the model to the checkpoint file
    """
    checkpoint_file = f'./checkpoint_{model.arch}.pth'
    
    model.class_to_idx = class_to_idx

    checkpoint = {
        'architecture': model.arch,
        'classifier': model.classifier,
        'class_to_idx': model.class_to_idx,
        'state_dict': model.state_dict()
    }
    
    torch.save(checkpoint, checkpoint_file)

def train(args, device):
    """
        This method trains the model based on the arguments
        and save the checkpoint file
    """
    # get the data dir
    data_dir = args.data_dir

    # set the dir variables for training, validation and testing
    train_dir = os.path.join(data_dir, 'train')
    valid_dir = os.path.join(data_dir, 'valid')
    test_dir  = os.path.join(data_dir, 'test')
    
    # Define your transforms for the training, validation, and testing sets
    data_transforms = {
        'train': transforms.Compose([transforms.RandomResizedCrop(224),
                                     transforms.RandomRotation(30),
                                     transforms.RandomHorizontalFlip(),
                                     transforms.ToTensor(),
                                     transforms.Normalize([0.485, 0.456, 0.406],
                                                          [0.229, 0.224, 0.225])
                                   ]),
        'valid': transforms.Compose([transforms.Resize(255),
                                     transforms.CenterCrop(224),
                                     transforms.ToTensor(),
                                     transforms.Normalize([0.485, 0.456, 0.406],
                                                          [0.229, 0.224, 0.225])
                                   ]), 
        'test': transforms.Compose([transforms.Resize(255),
                                     transforms.CenterCrop(224),
                                     transforms.ToTensor(),
                                     transforms.Normalize([0.485, 0.456, 0.406],
                                                          [0.229, 0.224, 0.225])
                                   ])
    }

    # Load the datasets with ImageFolder
    image_datasets = {
        'train': datasets.ImageFolder(train_dir, transform=data_transforms['train']),
        'valid': datasets.ImageFolder(train_dir, transform=data_transforms['valid']),
        'test': datasets.ImageFolder(train_dir, transform=data_transforms['test'])
    }

    # Using the image datasets and the transforms, define the dataloaders
    dataloaders = {
        'train': DataLoader(image_datasets['train'], batch_size=64, shuffle=True),
        'valid': DataLoader(image_datasets['valid'], batch_size=64),
        'test': DataLoader(image_datasets['test'], batch_size=64)
    }

    # choose the architecture and input features
    if args.arch == 'vgg16':
        model = models.vgg16(weights=VGG16_Weights.DEFAULT)
        input_features = model.classifier[0].in_features
    elif args.arch == 'densenet121':
        model = models.densenet121(weights=DenseNet121_Weights.DEFAULT)
        input_features = model.classifier.in_features
    elif args.arch == 'efficientnet_b0':
        model = models.efficientnet_b0(weights=EfficientNet_B0_Weights.DEFAULT)
        input_features = model.classifier[1].in_features    
    else:
        print(f"Unsupported {args.arch} architecture model argument, use default model 'vgg16'")
        args.arch = 'vgg16'
        model = models.vgg16(weights=VGG16_Weights.DEFAULT)
        input_features = model.classifier[0].in_features

    output_features = 102

    # freeze feature parameters for our model
    for param in model.features.parameters():
        param.requires_grad = False

    # creating a classifier and assign back to model
    classifier = nn.Sequential(nn.Linear(input_features, args.hidden_layers),
                               nn.ReLU(),
                               nn.Dropout(0.2),
                               nn.Linear(args.hidden_layers, output_features),
                               nn.LogSoftmax(dim=1))

    # set the classfier to model
    model.classifier = classifier

    # use the NLLLoss criterion
    criterion = nn.NLLLoss()

    # define optimizer """
    optimizer = optim.Adam(model.classifier.parameters(), lr=0.001)

    # based on the device, choose where to run the model training
    model.to(device)
    
    epochs = args.epochs
    validation_step = 0
    validation_after_steps = 34

    # iterate to each epochs for training
    for epoch in range(epochs):

        steps = 0
        running_loss = 0

        # use each labels and images for training
        for images, labels in tqdm(dataloaders['train'], leave=False, desc=f'Training epoch {epoch+1}'):

            steps += 1

            images, labels = images.to(device), labels.to(device)

            # set gradient to zero
            optimizer.zero_grad()

            # getting log probabilty from models
            logps = model(images)

            # calculate the loss
            loss = criterion(logps, labels)

            # do backward pass
            loss.backward()

            # optimizer steps
            optimizer.step()

            # accumulate the loss to running loss
            running_loss += loss.item()

            # run validation for every steps count trained
            if steps % validation_after_steps == 0:
                validation_step += 1
                val_loss = 0
                accuracy = 0

                # switching to evaluation mode
                model.eval()

                with torch.no_grad():
                    # validation loop
                    for v_image, v_label in tqdm(dataloaders['valid'], leave=False, desc=f'Validation {validation_step}'):
                        v_image, v_label = v_image.to(device), v_label.to(device)

                        v_logps = model(v_image)
                        batch_loss = criterion(v_logps, v_label)
                        val_loss += batch_loss.item()

                        # calculating accuracy
                        ps = torch.exp(v_logps)
                        top_p, top_class = ps.topk(1, dim=1)
                        equals = top_class == v_label.view(*top_class.shape)
                        accuracy += torch.mean(equals.type(torch.FloatTensor)).item()


                tqdm.write(f"Epoch: {epoch+1}/{epochs}, Validation: {validation_step}, "
                f"Training loss: {running_loss/validation_after_steps:.3f}, "
                f"Validation loss: {val_loss/len(dataloaders['valid']):.3f}, "
                f"Validation accuracy: {accuracy/len(dataloaders['valid']):.3f}")

                # revert back to training mode
                running_loss = 0
                model.train()

    # save the checkpoint
    model.arch = args.arch
    save_checkpoint(model, image_datasets['train'].class_to_idx)

    print(f"Model '{args.arch}' trained and checkpoint saved.")

def main():
    """
        The main function to parse the arguments and calls train method
        and finally prints time taken for training
    """
    # get the arguments using parser
    args = get_input_args()
    print(args)
    
    # set the device based on gpu flag and availability of gpu
    device = torch.device("cuda" if args.gpu and torch.cuda.is_available() else "cpu")
    
    # start time when training starts
    start_time = datetime.now()

    # call the train method to train and save the checkpoint
    train(args, device)

    # calculate elaped time
    elapsed_time = datetime.now() - start_time
    
    print(f"Time taken to train the model '{args.arch}': {elapsed_time}")
    

if __name__ == '__main__':
    main()
