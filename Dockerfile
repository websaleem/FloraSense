# Use the official AWS Lambda Python base image
FROM public.ecr.aws/lambda/python:3.12

# Set the working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Install system dependencies required for OpenCV/PIL if needed
RUN dnf update -y && dnf install -y \
    gcc \
    gcc-c++ \
    make \
    && dnf clean all

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . ${LAMBDA_TASK_ROOT}

# Explicitly copy checkpoints (since they might not be tracked by source control)
COPY checkpoint_*.pth ${LAMBDA_TASK_ROOT}/

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD ["lambda_handler.handler"]
