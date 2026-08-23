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

# ---- 1. Upload the site ----------------------------------------------------
# Syncs the whole directory, not just index.html: the site also has privacy.html
# and terms.html, and copying one file by name silently left those stale (or, on
# a first deploy, absent, so the footer links 404).
#
# Served no-cache so a redeploy is visible immediately. The pages are small and
# the expensive part (the model call) is never cached anyway. --delete keeps the
# bucket matching the repo, so a removed page actually disappears.
echo "📤 Step 1: Uploading website/ to s3://${BUCKET}/ ..."
aws s3 sync website/ "s3://${BUCKET}/" \
    --delete \
    --exclude "*" --include "*.html" \
    --content-type "text/html; charset=utf-8" \
    --cache-control "no-cache, must-revalidate" \
    --only-show-errors
echo "   ✓ Uploaded: $(ls website/*.html | xargs -n1 basename | tr '\n' ' ')"
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
    #
    # Done with parameter expansion rather than sed: BSD sed (macOS) does not
    # support \? in a basic regex, so the scheme survived, the second
    # expression then cut everything from the first slash, and the origin was
    # set to the literal "https:" -- which UpdateDistribution rejects with
    # "origin name cannot contain a colon". GNU sed on CI hid the difference.
    ORIGIN_HOST="${FUNCTION_URL#*://}"
    ORIGIN_HOST="${ORIGIN_HOST%%/*}"
    echo "   Origin host: ${ORIGIN_HOST}"
    echo ""

    # ---- 2b. Ensure an Origin Access Control for the Lambda origin ---------
    # The Function URL is AuthType: AWS_IAM, so every request must be SigV4
    # signed. CloudFront does that only when the origin has an OAC attached
    # with origin type "lambda"; without one, requests arrive unsigned and the
    # URL answers 403 -- the page loads and every prediction fails.
    echo "🔏 Step 2b: Ensuring Origin Access Control..."
    OAC_NAME="florasense-lambda-oac"
    OAC_ID=$(aws cloudfront list-origin-access-controls \
        --query "OriginAccessControlList.Items[?Name=='${OAC_NAME}'].Id | [0]" \
        --output text 2>/dev/null || true)

    if [[ -z "$OAC_ID" || "$OAC_ID" == "None" ]]; then
        OAC_ID=$(aws cloudfront create-origin-access-control \
            --origin-access-control-config "Name=${OAC_NAME},Description=SigV4 signing for the FloraSense Lambda Function URL,SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=lambda" \
            --query "OriginAccessControl.Id" --output text)
        echo "   ✓ Created OAC ${OAC_ID}."
    else
        echo "   ✓ Reusing OAC ${OAC_ID}."
    fi
    echo ""

    # ---- 2c. Origin request policy compatible with OAC ---------------------
    # OAC puts its SigV4 signature in the Authorization header. The managed
    # AllViewerExceptHostHeader policy excludes only Host, so it forwards the
    # viewer's Authorization -- which overwrites that signature, and since a
    # browser sends none, the request reaches Lambda unsigned and gets a 403
    # AccessDeniedException. There is no managed policy that drops both, so
    # this one excludes Host and Authorization and forwards everything else.
    echo "📋 Step 2c: Ensuring origin request policy..."
    ORP_NAME="florasense-lambda-origin-request"
    ORP_ID=$(aws cloudfront list-origin-request-policies \
        --query "OriginRequestPolicyList.Items[?OriginRequestPolicy.OriginRequestPolicyConfig.Name=='${ORP_NAME}'].OriginRequestPolicy.Id | [0]" \
        --output text 2>/dev/null || true)

    if [[ -z "$ORP_ID" || "$ORP_ID" == "None" ]]; then
        ORP_ID=$(aws cloudfront create-origin-request-policy \
            --origin-request-policy-config "$(cat <<JSON
{
  "Name": "${ORP_NAME}",
  "Comment": "Forwards everything except Host and Authorization, so CloudFront OAC signing survives.",
  "HeadersConfig": {
    "HeaderBehavior": "allExcept",
    "Headers": { "Quantity": 2, "Items": ["host", "authorization"] }
  },
  "CookiesConfig": { "CookieBehavior": "none" },
  "QueryStringsConfig": { "QueryStringBehavior": "all" }
}
JSON
)" --query "OriginRequestPolicy.Id" --output text)
        echo "   ✓ Created origin request policy ${ORP_ID}."
    else
        echo "   ✓ Reusing origin request policy ${ORP_ID}."
    fi
    echo ""

    # ---- 3. Patch the distribution -----------------------------------------
    echo "⚙️  Step 3: Configuring distribution..."
    aws cloudfront get-distribution-config --id "$DIST_ID" --output json > /tmp/fs-cf.json

    ORIGIN_HOST="$ORIGIN_HOST" LAMBDA_ORIGIN_ID="$LAMBDA_ORIGIN_ID" OAC_ID="$OAC_ID" ORP_ID="$ORP_ID" python3 - <<'PY'
import json, os

ORIGIN_HOST = os.environ["ORIGIN_HOST"]
ORIGIN_ID   = os.environ["LAMBDA_ORIGIN_ID"]
OAC_ID      = os.environ["OAC_ID"]
ORP_ID      = os.environ["ORP_ID"]

# Managed policy ids, confirmed against the CloudFront API.
CACHE_DISABLED = "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"   # Managed-CachingDisabled

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
    # Without this the origin is called anonymously and an AWS_IAM Function URL
    # returns 403 on every request.
    "OriginAccessControlId": OAC_ID,
})
cfg["Origins"]["Items"] = origins
cfg["Origins"]["Quantity"] = len(origins)
changes.append(f"origin {ORIGIN_ID} -> {ORIGIN_HOST} (OAC {OAC_ID})")

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
        "OriginRequestPolicyId": ORP_ID,
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
