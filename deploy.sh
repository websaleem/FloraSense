#!/bin/bash
set -euo pipefail

# ===========================================================================
#  FloraSense — One-command AWS deployment
#  Deploys CloudFormation stack, builds & pushes Docker image, updates Lambda.
# ===========================================================================

# ---- Configuration ----
AWS_REGION="ap-southeast-2"
STACK_NAME="florasense-stack"
APP_NAME="florasense"
IMAGE_TAG="latest"

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${APP_NAME}"

echo "🌸 Deploying FloraSense to AWS..."
echo "   Region:  ${AWS_REGION}"
echo "   Account: ${AWS_ACCOUNT_ID}"
echo ""

# ---- 1. Deploy / update CloudFormation stack ----
echo "📦 Step 1: Deploying CloudFormation stack (${STACK_NAME})..."
aws cloudformation deploy \
    --template-file cloudformation.yaml \
    --stack-name "${STACK_NAME}" \
    --parameter-overrides AppName="${APP_NAME}" ImageTag="${IMAGE_TAG}" \
    --capabilities CAPABILITY_NAMED_IAM \
    --region "${AWS_REGION}" \
    --no-fail-on-empty-changeset

echo "   ✓ Stack deployed."
echo ""

# ---- 2. Authenticate Docker to ECR ----
echo "🔑 Step 2: Authenticating Docker with ECR..."
aws ecr get-login-password --region "${AWS_REGION}" \
    | docker login --username AWS --password-stdin \
      "${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com"
echo ""

# ---- 3. Build the Docker image ----
echo "🐳 Step 3: Building Docker image..."
docker build --platform linux/amd64 -t "${APP_NAME}" .
echo ""

# ---- 4. Tag & push to ECR ----
echo "⬆️  Step 4: Pushing image to ECR..."
docker tag "${APP_NAME}:${IMAGE_TAG}" "${ECR_URI}:${IMAGE_TAG}"
docker push "${ECR_URI}:${IMAGE_TAG}"
echo ""

# ---- 5. Update Lambda to use the new image ----
LAMBDA_FUNCTION_NAME="${APP_NAME}-api"
echo "🔄 Step 5: Updating Lambda function (${LAMBDA_FUNCTION_NAME})..."
aws lambda update-function-code \
    --function-name "${LAMBDA_FUNCTION_NAME}" \
    --image-uri "${ECR_URI}:${IMAGE_TAG}" \
    --region "${AWS_REGION}" \
    --no-cli-pager

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
