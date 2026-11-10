#!/usr/bin/env bash
#
# Attach AWS's managed security-headers policy to the FloraSense distributions.
#
#   ./infra/cloudfront/apply-security-headers.sh
#
# WHY. The site ships a CSP in a <meta> tag, but sent no security response
# headers at all: no Strict-Transport-Security, no X-Content-Type-Options, no
# X-Frame-Options, no Referrer-Policy. SecureBin sends all four. The gap is
# not a code difference — FloraSense simply never had a response-headers
# policy attached.
#
# This is a custom policy rather than AWS's managed one, which was tried first.
# The managed policy sends X-Frame-Options: SAMEORIGIN and HSTS without
# includeSubDomains; SecureView, SecureBin, SkillView and Quizzee all send DENY
# and includeSubDomains, and FloraSense frames nothing, so there was no reason
# to be the weak one.
#
# It deliberately sets no Content-Security-Policy. The page already ships one in
# a <meta> tag, and when both are present the browser enforces the intersection
# — so a header CSP that did not exactly mirror the page's would silently break
# the site while looking like hardening.
#
# Attached to the default behaviour, which serves the site; /predict* and
# /health are JSON API behaviours where these headers do nothing useful.
#
# The distributions are not part of florasense-stack, which owns only the
# function, its repository and the invoke permissions, so this is applied here
# rather than in the template.
set -euo pipefail

# florasense-security-headers. Recreate with:
#   aws cloudfront create-response-headers-policy \
#     --response-headers-policy-config file://infra/cloudfront/security-headers-policy.json
POLICY_ID="ee0459f4-3edc-41c6-b91b-4fc2b5f3194a"
PROD="E2J826Z4CU0GAI"
DEV="E2KS7KR6VDA6ZP"

for ID in "$PROD" "$DEV"; do
  echo "== $ID"
  TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
  aws cloudfront get-distribution-config --id "$ID" > "$TMP/dist.json"
  ETAG="$(python3 -c "import json;print(json.load(open('$TMP/dist.json'))['ETag'])")"

  # `|| rc=$?` because set -e would otherwise abort on the deliberate exit 10
  # the script below uses to mean "already attached, nothing to do".
  rc=0
  python3 - "$TMP/dist.json" "$TMP/cfg.json" "$POLICY_ID" <<'PY' || rc=$?
import json, sys
src, dst, policy = sys.argv[1], sys.argv[2], sys.argv[3]
cfg = json.load(open(src))['DistributionConfig']
current = cfg['DefaultCacheBehavior'].get('ResponseHeadersPolicyId')
if current == policy:
    print('   already attached'); raise SystemExit(10)
cfg['DefaultCacheBehavior']['ResponseHeadersPolicyId'] = policy
json.dump(cfg, open(dst, 'w'))
print(f'   attaching (was: {current})')
PY
  if [ "$rc" -eq 10 ]; then continue; fi
  if [ "$rc" -ne 0 ]; then echo "   failed to build config (exit $rc)"; exit 1; fi

  aws cloudfront update-distribution --id "$ID" --if-match "$ETAG" \
      --distribution-config "file://$TMP/cfg.json" \
      --query "Distribution.Status" --output text
done

echo
echo "Deploying takes a few minutes. Then check with:"
echo "  curl -sI https://florasense.websaleem.com/ | grep -iE 'strict-transport|x-content-type|x-frame|referrer'"
