// CloudFront Function (viewer-request) for the /predict* behaviour.
//
// WHAT IT FIXES. /predict reaches the Lambda Function URL through an Origin
// Access Control, which SigV4-signs every origin request. CloudFront never
// reads the request body, so it signs whatever payload hash the viewer
// supplies — and a Lambda Function URL with IAM auth refuses a request whose
// payload hash does not match the bytes it received. A POST that omits
// x-amz-content-sha256 is therefore rejected at the origin with
//
//     403 {"message":"The request signature we calculated does not match
//          the signature you provided. Check your AWS Secret Access Key..."}
//
// which is actively misleading: the caller has no AWS secret key, is not
// expected to have one, and nothing they can do with credentials will help.
// The actual requirement is one header. This turns that into a 400 that says
// so.
//
// WHY NOT JUST ACCEPT THE REQUEST. There is no server-side way to. The hash
// must be computed over the exact body bytes, and only the client has them
// before the request is sent. The UNSIGNED-PAYLOAD sentinel that S3 accepts is
// rejected here — verified against the live endpoint — so there is no sentinel
// to substitute either. Dropping OAC would make the Function URL publicly
// invokable, which is the thing OAC exists to prevent.
//
// WHO THIS AFFECTS. Not the website and not the Android app: both build the
// multipart body by hand and send its SHA-256, because FormData picks its own
// boundary and will not reveal the exact bytes it produced. It affects anyone
// calling the API directly — a curl, a script, a future client — who would
// otherwise spend a long time looking for a credentials problem that does not
// exist.
// DEPLOYING IT. The distributions are not part of florasense-stack — the stack
// only owns the function, its ECR repository and the invoke permission, and
// takes the distribution ids as parameters. So this is attached by hand, to the
// /predict* behaviour of both, as a viewer-request association:
//
//   aws cloudfront create-function --name florasense-predict-guard \
//     --function-config '{"Comment":"...","Runtime":"cloudfront-js-2.0"}' \
//     --function-code fileb://infra/cloudfront/predict-guard.js
//   aws cloudfront publish-function --name florasense-predict-guard --if-match <etag>
//
// then, for each of E2J826Z4CU0GAI (prod) and E2KS7KR6VDA6ZP (dev), add to the
// /predict* cache behaviour:
//
//   "FunctionAssociations": {"Quantity": 1, "Items": [
//     {"FunctionARN": "<published arn>", "EventType": "viewer-request"}]}
//
// After changing this file, re-upload with update-function and publish again:
// editing the file alone changes nothing that is serving traffic.
function handler(event) {
  var request = event.request;

  // Only bodied methods are affected. GET /health and friends sign fine
  // because there is no payload to disagree about.
  if (request.method !== 'POST' && request.method !== 'PUT' && request.method !== 'PATCH') {
    return request;
  }

  // Header names in CloudFront Functions are always lowercased.
  if (request.headers['x-amz-content-sha256']) {
    return request;
  }

  return {
    statusCode: 400,
    statusDescription: 'Bad Request',
    headers: {
      'content-type': { value: 'application/json' },
      'cache-control': { value: 'no-store' }
    },
    body: JSON.stringify({
      detail:
        'This endpoint is reached through CloudFront Origin Access Control, which signs ' +
        'the request to the origin but cannot see the body. Send the SHA-256 of the exact ' +
        'request body, lowercase hex, in the x-amz-content-sha256 header. Build the ' +
        'multipart body yourself rather than using FormData, which hides the bytes it ' +
        'produced. See the README for a worked example.'
    })
  };
}
