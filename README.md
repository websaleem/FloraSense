# image-classifier
This repository contains python project code and associated files for the RMIT's AI Programming with Python Nanodegree program conducted by Udacity. This is an image classfier project which uses it own training of the classifier using flower dataset, it was completed as a part of RMIT's AI Programming with Python
This repository consists of all the corresponding image labels, sample images for testing and various coding exercises to complete the course.

## Table Of Contents

### Tutorial Notebooks
* The notebook file can be used to train and test the image.

### Programming Project
* [Intro to Python Project - Image Classifier:](https://github.com/websaleem/image-classifier) This project allows users to train one of the models ['vgg16', 'densenet121', 'efficientnet_b0'] using flower data-set [download](https://s3.amazonaws.com/content.udacity-data.com/nd089/flower_data.tar.gz) and predict the flower image class and probabilites, it also prints the top-k class and probabilites.

### How to Run?
* Training help:
workspace$ python train.py -h
usage: train.py [-h] [--arch ARCH] [--learning_rate LEARNING_RATE] [--hidden_layers HIDDEN_LAYERS]
                [--epochs EPOCHS] [--gpu]
                data_dir

Tranining an Image Classifier.

positional arguments:
  data_dir              Directory of the dataset (i.e. flowers)

options:
  -h, --help            show this help message and exit
  --arch ARCH           Choose the model acrchitecture from ["vgg16", "densenet121", "efficientnet_b0"]
  --learning_rate LEARNING_RATE
                        Learning rate
  --hidden_layers HIDDEN_LAYERS
                        Number of hidden layers
  --epochs EPOCHS       epochs to run
  --gpu                 Use gpu if available

* Prediction help:
usage: predict.py [-h] [--arch ARCH] [--top_k TOP_K] [--category_names CATEGORY_NAMES] [--gpu]
                  image_path

Predict flower name using a trained model.

positional arguments:
  image_path            Path to test image flower.

options:
  -h, --help            show this help message and exit
  --arch ARCH           Choose the model acrchitecture from ["vgg16", "densenet121", "efficientnet_b0"]
  --top_k TOP_K         Returns top K predictions
  --category_names CATEGORY_NAMES
                        Path of JSON file having class name mapping.
  --gpu                 Use gpu if available
  
## Dependencies

Each directory has a `requirements.txt` describing the minimal dependencies required to run the notebooks in that directory.

### pip

To install these dependencies with pip, you can issue `pip3 install -r requirements.txt`.
