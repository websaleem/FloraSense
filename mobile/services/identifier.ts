import { CryptoDigestAlgorithm, digest } from 'expo-crypto';
import { File } from 'expo-file-system';
import { fetch } from 'expo/fetch';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import { API_BASE, MAX_IMAGE_PX, TOP_K } from '../constants/config';
import { Prediction } from '../types';
import { deleteQuietly } from './files';

/** A failure whose message is safe to show the user as-is. */
export class IdentifyError extends Error {}

const REQUEST_TIMEOUT_MS = 60_000;

/**
 * Resize to MAX_IMAGE_PX on the longest edge and re-encode as JPEG, so a
 * full-resolution camera frame never leaves the device. Returns the URI of a
 * temporary file the caller must delete.
 */
async function prepareImage(imageUri: string): Promise<string> {
  const source = await ImageManipulator.manipulate(imageUri).renderAsync();
  const longSide = Math.max(source.width, source.height);
  const resized = longSide > MAX_IMAGE_PX
    ? await ImageManipulator.manipulate(source)
        .resize(source.width >= source.height ? { width: MAX_IMAGE_PX } : { height: MAX_IMAGE_PX })
        .renderAsync()
    : source;
  const { uri } = await resized.saveAsync({ compress: 0.85, format: SaveFormat.JPEG });
  return uri;
}

function toHex(buffer: ArrayBuffer): string {
  return Array.from(new Uint8Array(buffer), b => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Build a multipart/form-data body by hand.
 *
 * The API sits behind a CloudFront Origin Access Control that SigV4-signs each
 * request to Lambda. CloudFront does not read the body, so it signs whatever
 * payload hash the client supplies in x-amz-content-sha256, and Lambda function
 * URLs reject unsigned payloads — so the hash is mandatory and must match the
 * exact bytes sent. FormData chooses its own boundary and never exposes those
 * bytes, which is why the body is assembled here instead.
 */
async function buildSignedMultipart(jpeg: Uint8Array) {
  const boundary = `----FloraSense${Date.now().toString(16)}${Math.random().toString(16).slice(2)}`;
  const encoder = new TextEncoder();
  const head = encoder.encode(
    `--${boundary}\r\n` +
    'Content-Disposition: form-data; name="file"; filename="capture.jpg"\r\n' +
    'Content-Type: image/jpeg\r\n\r\n',
  );
  const tail = encoder.encode(`\r\n--${boundary}--\r\n`);

  const body = new Uint8Array(head.length + jpeg.length + tail.length);
  body.set(head, 0);
  body.set(jpeg, head.length);
  body.set(tail, head.length + jpeg.length);

  const hash = toHex(await digest(CryptoDigestAlgorithm.SHA256, body));
  return { body, boundary, hash };
}

/** Accept only well-formed predictions; the API is trusted, but not blindly. */
function parsePredictions(payload: unknown): Prediction[] {
  const raw = (payload as { predictions?: unknown })?.predictions;
  if (!Array.isArray(raw)) {
    throw new IdentifyError('FloraSense returned an unexpected response. Please try again.');
  }
  const predictions = raw
    .filter((p): p is { class_id: unknown; flower_name: unknown; probability: unknown } =>
      !!p && typeof p === 'object')
    .map(p => ({
      classId: String(p.class_id ?? ''),
      name: typeof p.flower_name === 'string' ? p.flower_name : 'Unknown',
      probability: Number(p.probability),
    }))
    .filter(p => Number.isFinite(p.probability) && p.probability >= 0 && p.probability <= 1);

  if (predictions.length === 0) {
    throw new IdentifyError('FloraSense could not identify this image. Please try another photo.');
  }
  return predictions;
}

function messageForStatus(status: number): string {
  switch (status) {
    case 400:
    case 422:
      return 'That image could not be processed. Please try a different photo.';
    case 429:
      return 'FloraSense is busy right now. Please try again in a moment.';
    case 403:
      // A signature mismatch here means the upload bytes and the hash disagree,
      // or the app is pointed at the raw origin — a build problem, not the user's.
      return 'FloraSense could not verify the upload. Please update the app or try again later.';
    case 502:
    case 503:
    case 504:
      return 'FloraSense is starting up or busy. Please try again in a moment.';
    default:
      return 'FloraSense could not identify the flower due to a problem on our end.';
  }
}

export async function identifyFlower(imageUri: string): Promise<Prediction[]> {
  const preparedUri = await prepareImage(imageUri);
  try {
    const jpeg = await new File(preparedUri).bytes();
    const { body, boundary, hash } = await buildSignedMultipart(jpeg);

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

    let response;
    try {
      response = await fetch(`${API_BASE}/predict?top_k=${TOP_K}`, {
        method: 'POST',
        headers: {
          'Content-Type': `multipart/form-data; boundary=${boundary}`,
          'x-amz-content-sha256': hash,
        },
        body,
        signal: controller.signal,
      });
    } catch (err) {
      if (controller.signal.aborted) {
        throw new IdentifyError('FloraSense took too long to respond. Please try again.');
      }
      throw new IdentifyError('Could not reach FloraSense. Check your internet connection.');
    } finally {
      clearTimeout(timer);
    }

    if (!response.ok) {
      throw new IdentifyError(messageForStatus(response.status));
    }
    return parsePredictions(await response.json());
  } finally {
    deleteQuietly(preparedUri);
  }
}
