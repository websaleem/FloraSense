#!/bin/bash
set -euo pipefail

# ===========================================================================
#  FloraSense — One-command AWS deployment
#  Deploys CloudFormation stack, builds & pushes Docker image, updates Lambda.
#
#  Ordering matters here. The Lambda's ImageUri points into the ECR repository
#  that the same stack creates, so on a first deploy there is no image to point
#  at and stack creation rolls back. The stack is therefore applied in two
#  passes: bootstrap the repository, push an image, then create the function.
#  Both passes are idempotent, so re-running this script is safe.
# ===========================================================================

# Paths below are repo-root-relative, and the Docker build context is the repo
# root, so anchor there rather than depending on the caller's directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

# ---- Configuration ----
AWS_REGION="ap-southeast-2"
STACK_NAME="florasense-stack"
APP_NAME="florasense"
IMAGE_TAG="latest"
ARCH="${ARCH:-efficientnet_b0}"

LAMBDA_FUNCTION_NAME="${APP_NAME}-api"
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"

echo "🌸 Deploying FloraSense to AWS..."
echo "   Region:  ${AWS_REGION}"
echo "   Account: ${AWS_ACCOUNT_ID}"
echo "   Arch:    ${ARCH}"
echo ""

# ---- 0. Preflight ----
# Fail here rather than three minutes into a Docker build, or worse, at the
# first prediction request with a 503 from a function that has no model.
#
# Search order mirrors model_utils.resolve_checkpoint_path(): the best-scoring
# weights, then the end-of-training ones, then the legacy single-file name from
# before training tagged its output. Whatever is chosen is passed to the build,
# so the image ships exactly the checkpoint reported here.
CHECKPOINT=""
for candidate in "checkpoints/checkpoint_${ARCH}_best.pth" \
                 "checkpoints/checkpoint_${ARCH}_latest.pth" \
                 "checkpoints/checkpoint_${ARCH}.pth"; do
    if [[ -f "${candidate}" ]]; then
        CHECKPOINT="${candidate}"
        break
    fi
done

if [[ -z "${CHECKPOINT}" ]]; then
    echo "❌ No checkpoint for '${ARCH}' found in ${REPO_ROOT}/checkpoints/."
    echo "   Looked for: checkpoint_${ARCH}_best.pth, checkpoint_${ARCH}_latest.pth, checkpoint_${ARCH}.pth"
    echo "   Train one first:  python training/train.py data/flowers --arch ${ARCH}"
    exit 1
fi
command -v docker >/dev/null 2>&1 || { echo "❌ docker is not installed."; exit 1; }
docker info >/dev/null 2>&1 || { echo "❌ docker daemon is not running."; exit 1; }
echo "   ✓ Preflight passed (using ${CHECKPOINT}, docker running)."
echo ""

# ---- 1. Bootstrap: does the function already exist? ----
# On a first run it does not, so the first pass must create only the ECR
# repository. On later runs it does, and passing 'false' would DELETE it — so
# the flag is derived from reality rather than hardcoded.
if aws lambda get-function --function-name "${LAMBDA_FUNCTION_NAME}" \
       --region "${AWS_REGION}" >/dev/null 2>&1; then
    FIRST_PASS="true"
    echo "📦 Step 1: Stack exists — updating in place."
else
    FIRST_PASS="false"
    echo "📦 Step 1: First deploy — creating ECR repository only."
fi

aws cloudformation deploy \
    --template-file infra/florasense-api.yml \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides AppName="${APP_NAME}" ImageTag="${IMAGE_TAG}" \
                          Arch="${ARCH}" DeployFunction="${FIRST_PASS}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset

echo "   ✓ Repository ready."
echo ""

# ---- 2. Authenticate Docker to ECR ----
echo "🔑 Step 2: Authenticating Docker with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin \
      "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo ""

# ---- 3/4. Build and push the Docker image ----
# --provenance=false --sbom=false are load-bearing, not hygiene. Buildx attaches
# provenance and SBOM attestations by default, which turns the push into an OCI
# *image index* holding the real linux/amd64 manifest alongside an attestation
# manifest with platform unknown/unknown. Lambda cannot consume an index and
# rejects the image with "The image manifest, config or layer media type for the
# source image ... is not supported" -- at stack-create time, long after the
# build appears to have succeeded.
#
# Pushing straight from buildx also skips loading a multi-GB image into the local
# Docker store first, which matters on a machine that is tight on disk.
echo "🐳 Step 3: Building and pushing image (arch=${ARCH}, checkpoint=${CHECKPOINT})..."
docker buildx build \
    --platform linux/amd64 \
    --provenance=false \
    --sbom=false \
    --build-arg ARCH="${ARCH}" \
    --build-arg CHECKPOINT="${CHECKPOINT}" \
    --file backend/lambda/Dockerfile \
    --tag "${ECR_URI}:${IMAGE_TAG}" \
    --push \
    .
echo ""

# ---- 5. Create or update the function ----
# Second pass: now that an image exists, the function can be created. On an
# existing stack the template is unchanged (ImageUri is still :latest), so
# CloudFormation reports no changes and the explicit code update below is what
# actually rolls the new image out.
echo "🔄 Step 5: Deploying Lambda function..."
aws cloudformation deploy \
    --template-file infra/florasense-api.yml \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides AppName="${APP_NAME}" ImageTag="${IMAGE_TAG}" \
                          Arch="${ARCH}" DeployFunction="true" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset

if [[ "${FIRST_PASS}" == "true" ]]; then
    aws lambda update-function-code \
        --function-name "${LAMBDA_FUNCTION_NAME}" \
        --image-uri "${ECR_URI}:${IMAGE_TAG}" \
        --region "${AWS_REGION}" \
        --no-cli-pager >/dev/null
    aws lambda wait function-updated \
        --function-name "${LAMBDA_FUNCTION_NAME}" --region "${AWS_REGION}"
    echo "   ✓ Function code updated."
fi
echo ""

# ---- 6. Print the live Function URL ----
FUNCTION_URL=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}" \
    --region "${AWS_REGION}" \
    --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" \
    --output text)

echo "============================================"
echo "✅ FloraSense deployed successfully!"
echo ""
echo "🌐 Live URL: ${FUNCTION_URL}"
echo "🏥 Health:   ${FUNCTION_URL}health"
echo "============================================"
