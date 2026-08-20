#!/bin/bash
set -euo pipefail

# ===========================================================================
#  FloraSense — publish the web front end and wire CloudFront to the API
#
#  Serves the page from S3 and routes only /predict and /health to the Lambda
#  Function URL, on the same domain. Same-origin means the page's relative
#  fetch('/predict') needs no change and no CORS configuration exists to drift.
#  It also means a cold Lambda no longer delays *seeing* the app -- the page is
#  edge-cached and loads instantly; only the first prediction pays the cold start.
#
#  Distribution ids and *.cloudfront.net domains are deliberately NOT hardcoded:
#  they are scrub targets in expressions.txt, so they arrive as arguments.
#
#  Usage:
#    ./scripts/deploy-web.sh --bucket dev.florasense.websaleem.com \
#                            --distribution-id EXXXXXXXXXXXXX \
#                            [--function-url https://xxxx.lambda-url.ap-southeast-2.on.aws/]
#
#  --function-url is optional; without it the URL is read from the CloudFormation
#  stack output. Pass --content-only to skip the distribution config entirely.
# ===========================================================================

# website/ is repo-root-relative, so anchor there rather than depending on the
# caller's directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_ROOT}"

AWS_REGION="ap-southeast-2"
STACK_NAME="florasense-stack"
LAMBDA_ORIGIN_ID="florasense-lambda-api"

BUCKET=""; DIST_ID=""; FUNCTION_URL=""; CONTENT_ONLY="false"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --bucket)          BUCKET="$2"; shift 2 ;;
    --distribution-id) DIST_ID="$2"; shift 2 ;;
    --function-url)    FUNCTION_URL="$2"; shift 2 ;;
    --content-only)    CONTENT_ONLY="true"; shift ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done
[[ -n "$BUCKET"  ]] || { echo "❌ --bucket is required"; exit 1; }
[[ -n "$DIST_ID" ]] || { echo "❌ --distribution-id is required"; exit 1; }

echo "🌸 Publishing FloraSense web front end..."
echo "   Bucket:       ${BUCKET}"
echo "   Distribution: ${DIST_ID}"
echo ""

# ---- 1. Upload the page ----------------------------------------------------
# index.html is served with no-cache so a redeploy is visible immediately;
# the page is small and the expensive part (the model call) is never cached.
echo "📤 Step 1: Uploading website/ to s3://${BUCKET}/ ..."
aws s3 cp website/index.html "s3://${BUCKET}/index.html" \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, must-revalidate" \
    --only-show-errors
echo "   ✓ Uploaded."
echo ""

if [[ "$CONTENT_ONLY" == "true" ]]; then
    echo "⏭  Skipping distribution config (--content-only)."
else
    # ---- 2. Resolve the Function URL ---------------------------------------
    if [[ -z "$FUNCTION_URL" ]]; then
        echo "🔍 Step 2: Reading Function URL from stack ${STACK_NAME}..."
        FUNCTION_URL=$(aws cloudformation describe-stacks \
            --stack-name "${STACK_NAME}" --region "${AWS_REGION}" \
            --query "Stacks[0].Outputs[?OutputKey=='FunctionUrl'].OutputValue" \
            --output text 2>/dev/null || true)
        [[ -n "$FUNCTION_URL" && "$FUNCTION_URL" != "None" ]] || {
            echo "❌ No Function URL found. Deploy the backend first (./scripts/deploy-backend.sh),"
            echo "   or pass --function-url explicitly."; exit 1; }
    fi
    # CloudFront wants a bare host: no scheme, no trailing slash.
    ORIGIN_HOST=$(echo "$FUNCTION_URL" | sed -e 's|^https\?://||' -e 's|/.*$||')
    echo "   Origin host: ${ORIGIN_HOST}"
    echo ""

    # ---- 3. Patch the distribution -----------------------------------------
    echo "⚙️  Step 3: Configuring distribution..."
    aws cloudfront get-distribution-config --id "$DIST_ID" --output json > /tmp/fs-cf.json

    ORIGIN_HOST="$ORIGIN_HOST" LAMBDA_ORIGIN_ID="$LAMBDA_ORIGIN_ID" python3 - <<'PY'
import json, os

ORIGIN_HOST = os.environ["ORIGIN_HOST"]
ORIGIN_ID   = os.environ["LAMBDA_ORIGIN_ID"]

# Managed policy ids, confirmed against the CloudFront API.
CACHE_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"   # Managed-CachingDisabled
# AllViewerExceptHostHeader forwards everything the viewer sent EXCEPT Host.
# A Lambda Function URL rejects a foreign Host header, so forwarding it breaks
# every request through the distribution.
ORP_NO_HOST    = "b689b0a8-53d0-40ab-baf2-68738e2966ac"

doc  = json.load(open("/tmp/fs-cf.json"))
etag = doc["ETag"]
cfg  = doc["DistributionConfig"]

changes = []

# 3a. Default root object -- an empty value is why "/" returns 403 today.
if cfg.get("DefaultRootObject") != "index.html":
    cfg["DefaultRootObject"] = "index.html"
    changes.append("DefaultRootObject=index.html")

# 3b. Lambda origin (replace in place if it already exists, so this is idempotent)
origins = cfg["Origins"]["Items"]
origins = [o for o in origins if o["Id"] != ORIGIN_ID]
origins.append({
    "Id": ORIGIN_ID,
    "DomainName": ORIGIN_HOST,
    "OriginPath": "",
    "CustomHeaders": {"Quantity": 0},
    "CustomOriginConfig": {
        "HTTPPort": 80,
        "HTTPSPort": 443,
        "OriginProtocolPolicy": "https-only",
        "OriginSslProtocols": {"Quantity": 1, "Items": ["TLSv1.2"]},
        # 60s is the maximum without a support request, and it is needed: a cold
        # container-image Lambda loading torch can take 10-15s before it even
        # begins inference. The 30s default would surface as an intermittent 504
        # on exactly the first request a new user makes.
        "OriginReadTimeout": 60,
        "OriginKeepaliveTimeout": 5,
    },
    "ConnectionAttempts": 3,
    "ConnectionTimeout": 10,
    "OriginShield": {"Enabled": False},
})
cfg["Origins"]["Items"] = origins
cfg["Origins"]["Quantity"] = len(origins)
changes.append(f"origin {ORIGIN_ID} -> {ORIGIN_HOST}")

# 3c. Route the API paths to that origin. POST is the whole point: the existing
# distribution allows only GET/HEAD, so /predict cannot work without this.
def behavior(pattern):
    return {
        "PathPattern": pattern,
        "TargetOriginId": ORIGIN_ID,
        "ViewerProtocolPolicy": "https-only",
        "AllowedMethods": {
            "Quantity": 7,
            "Items": ["GET", "HEAD", "POST", "PUT", "PATCH", "OPTIONS", "DELETE"],
            "CachedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]},
        },
        "Compress": True,
        "CachePolicyId": CACHE_DISABLED,
        "OriginRequestPolicyId": ORP_NO_HOST,
        "SmoothStreaming": False,
        "FieldLevelEncryptionId": "",
        "LambdaFunctionAssociations": {"Quantity": 0},
        "FunctionAssociations": {"Quantity": 0},
    }

wanted   = ["/predict*", "/health"]
existing = cfg.get("CacheBehaviors", {}).get("Items", [])
existing = [b for b in existing if b.get("PathPattern") not in wanted]
existing = [behavior(p) for p in wanted] + existing
cfg["CacheBehaviors"] = {"Quantity": len(existing), "Items": existing}
changes.append("behaviors " + ", ".join(wanted) + " -> lambda (POST allowed, no cache)")

json.dump(cfg, open("/tmp/fs-cf-new.json", "w"), indent=2)
open("/tmp/fs-cf-etag", "w").write(etag)
print("   Changes:")
for c in changes:
    print(f"     - {c}")
PY

    ETAG=$(cat /tmp/fs-cf-etag)
    aws cloudfront update-distribution \
        --id "$DIST_ID" \
        --distribution-config "file:///tmp/fs-cf-new.json" \
        --if-match "$ETAG" \
        --output json > /dev/null
    echo "   ✓ Distribution updated."
    echo ""
fi

# ---- 4. Invalidate -------------------------------------------------------
echo "♻️  Step 4: Invalidating edge caches..."
INVALIDATION=$(aws cloudfront create-invalidation \
    --distribution-id "$DIST_ID" --paths "/*" \
    --query "Invalidation.Id" --output text)
echo "   ✓ Invalidation ${INVALIDATION} created."
echo ""

ALIAS=$(aws cloudfront get-distribution-config --id "$DIST_ID" \
        --query "DistributionConfig.Aliases.Items[0]" --output text 2>/dev/null || echo "")
echo "============================================"
echo "✅ Web front end published!"
[[ -n "$ALIAS" && "$ALIAS" != "None" ]] && {
    echo ""
    echo "🌐 Site:   https://${ALIAS}/"
    echo "🏥 Health: https://${ALIAS}/health"
}
echo ""
echo "Deployment takes a few minutes to propagate to all edges."
echo "============================================"
