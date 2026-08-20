# Use the official AWS Lambda Python base image
#
# Build context is the REPOSITORY ROOT, not this directory, because the image
# needs backend/lambda/, website/ and one file from checkpoints/. Build it as:
#   docker buildx build -f backend/lambda/Dockerfile .
# which is what scripts/deploy-backend.sh does. Every COPY below is therefore
# written relative to the repo root.
FROM public.ecr.aws/lambda/python:3.12

# Which architecture's checkpoint gets baked into this image. Must match the
# ARCH environment variable the function runs with, or load_checkpoint() finds
# nothing and every /predict returns 503 at request time rather than failing
# the build. Keep in sync with the Arch parameter in infra/florasense-api.yml.
ARG ARCH=efficientnet_b0

# Which checkpoint file gets baked in. Kept separate from ARCH because training
# writes checkpoint_{arch}_best.pth and checkpoint_{arch}_latest.pth, while
# older runs wrote checkpoint_{arch}.pth — there is no single name to derive.
# scripts/deploy-backend.sh resolves it (best, then latest, then legacy) and
# passes it here as a path relative to the build context, which is the repo root.
ARG CHECKPOINT=checkpoints/checkpoint_efficientnet_b0.pth

# Set the working directory
WORKDIR ${LAMBDA_TASK_ROOT}

# Install system dependencies required for OpenCV/PIL if needed
RUN dnf update -y && dnf install -y \
    gcc \
    gcc-c++ \
    make \
    && dnf clean all

# Copy requirements file first to leverage Docker cache
COPY backend/lambda/requirements.txt .

# Install the CPU-only build of torch before anything else. The default wheels
# bundle CUDA libraries worth well over a gigabyte that Lambda can never use —
# they inflate the image and lengthen cold start. Installing these first means
# the torch>=2.0.0 pin below is already satisfied and pip leaves them alone.
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch torchvision

# Install the remaining dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Fail now, not on the first prediction, if the checkpoint does not belong to
# the architecture the function will run with. Mismatched weights clear the
# build and clear startup, then surface as a load_state_dict size mismatch on a
# cold start — a long way from the flag that caused it.
RUN case "${CHECKPOINT}" in \
      *"${ARCH}"*) echo "checkpoint ${CHECKPOINT} matches arch ${ARCH}" ;; \
      *) echo "ERROR: CHECKPOINT=${CHECKPOINT} is not a checkpoint for ARCH=${ARCH}" >&2; exit 1 ;; \
    esac

# Copy the application code file by file rather than `COPY . ${LAMBDA_TASK_ROOT}`.
# A blanket copy pulled every checkpoint in the build context into the image
# layer — and deleting them in a later step does not shrink the layer that
# already holds them. That is why the other architectures were excluded in
# .dockerignore, and why building any arch but efficientnet_b0 failed on the
# COPY below. Listing what the runtime actually imports keeps the image small
# for every arch without excluding anything from the context.
COPY backend/lambda/model_utils.py ${LAMBDA_TASK_ROOT}/

# Pre-download the torchvision ImageNet weights at build time. build_model()
# constructs the architecture with pretrained weights before load_checkpoint()
# overwrites them, so without this the function would reach out to
# download.pytorch.org on every cold start and try to cache into a read-only
# HOME. Baking them in removes both the failure and ~20 MB of cold-start I/O.
#
# Driven through build_model() so it fetches weights for whichever ARCH is being
# built. This step hardcoded efficientnet_b0, so a vgg16 or densenet121 image
# baked in weights it never uses and still downloaded the right ones at runtime.
ENV TORCH_HOME=${LAMBDA_TASK_ROOT}/.torch
RUN python -c "from model_utils import build_model; build_model('${ARCH}')"

COPY backend/lambda/lambda_handler.py backend/lambda/cat_to_name.json ${LAMBDA_TASK_ROOT}/

# Serve the web UI from where lambda_handler expects it. The handler reads
# static/index.html, but the source of truth lives in website/ — without this
# copy the directory is created empty at startup and GET / raises
# FileNotFoundError.
COPY website/ ${LAMBDA_TASK_ROOT}/static/

# The checkpoint goes in model/, NOT the task root. To Python a *.pth file is a
# "path configuration file": site.addsitedir() runs over LAMBDA_TASK_ROOT at
# interpreter start and parses every *.pth there as UTF-8 text. A binary torch
# checkpoint makes that raise UnicodeDecodeError and the runtime exits 1 before
# any handler code executes — the failure looks like a broken image, not a
# misplaced file. addsitedir only scans one level, so a subdirectory is safe,
# and TORCH_HOME above caches under .torch/hub/ for the same reason.
#
# Copied last: it is by far the largest layer and the one that changes whenever
# a model is retrained, so every cacheable step sits above it.
COPY ${CHECKPOINT} ${LAMBDA_TASK_ROOT}/model/

# Set the CMD to your handler (could also be done as a parameter override outside of the Dockerfile)
CMD ["lambda_handler.handler"]
