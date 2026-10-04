#!/usr/bin/env bash
#
# Identify a flower from the command line.
#
#   ./scripts/predict.sh flower.jpg [top_k]
#
# Why this is not a one-line `curl -F`: the API sits behind CloudFront Origin
# Access Control, which SigV4-signs the origin request but never reads the
# body, so the caller has to supply the body's SHA-256 in x-amz-content-sha256
# or the Lambda Function URL rejects the request. That means the multipart
# body has to be built here — curl's own -F picks a boundary internally and
# will not tell us the exact bytes it sent, so there is nothing to hash.
set -euo pipefail
IMG="$1"; TOP_K="${2:-5}"
BOUNDARY="florasense$(date +%s)"
BODY="$(mktemp)"; trap 'rm -f "$BODY"' EXIT

# The API requires an image/* part; octet-stream is rejected with a 400.
case "${IMG##*.}" in
  png|PNG)   CTYPE=image/png ;;
  webp|WEBP) CTYPE=image/webp ;;
  *)         CTYPE=image/jpeg ;;
esac

{
  printf -- '--%s\r\n' "$BOUNDARY"
  printf 'Content-Disposition: form-data; name="file"; filename="%s"\r\n' "$(basename "$IMG")"
  printf 'Content-Type: %s\r\n\r\n' "$CTYPE"
  cat "$IMG"
  printf '\r\n--%s--\r\n' "$BOUNDARY"
} > "$BODY"

HASH=$(shasum -a 256 "$BODY" | cut -d' ' -f1)

curl -sS -X POST "https://florasense.websaleem.com/predict?top_k=${TOP_K}" \
  -H "Content-Type: multipart/form-data; boundary=${BOUNDARY}" \
  -H "x-amz-content-sha256: ${HASH}" \
  --data-binary @"$BODY"
