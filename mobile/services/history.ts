import AsyncStorage from '@react-native-async-storage/async-storage';
import { Directory, File, Paths } from 'expo-file-system';
import { MAX_HISTORY } from '../constants/config';
import { Prediction, ScanRecord } from '../types';
import { deleteQuietly } from './files';

const HISTORY_KEY = 'scan_history';
const IMAGES_DIR = 'scan_images';

function imagesDir(): Directory {
  const dir = new Directory(Paths.document, IMAGES_DIR);
  if (!dir.exists) {
    dir.create();
  }
  return dir;
}

/** Copy a photo into app-private storage so history survives cache clearing. */
export function saveImageLocally(imageUri: string, id: string): string {
  const dest = new File(imagesDir(), `${id}.jpg`);
  new File(imageUri).copy(dest);
  return dest.uri;
}

/** True only for photos this app saved itself — never an arbitrary path from a param. */
export function isHistoryImage(uri: string | undefined): uri is string {
  return !!uri && uri.startsWith('file://') && uri.includes(`/${IMAGES_DIR}/`);
}

function isPrediction(p: unknown): p is Prediction {
  const v = p as Prediction;
  return !!v && typeof v.name === 'string' && typeof v.probability === 'number';
}

function isRecord(r: unknown): r is ScanRecord {
  const v = r as ScanRecord;
  return !!v
    && typeof v.id === 'string'
    && typeof v.timestamp === 'number'
    && typeof v.imageUri === 'string'
    && Array.isArray(v.predictions)
    && v.predictions.every(isPrediction);
}

export async function getHistory(): Promise<ScanRecord[]> {
  const raw = await AsyncStorage.getItem(HISTORY_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.filter(isRecord) : [];
  } catch {
    return [];
  }
}

export async function addToHistory(record: ScanRecord): Promise<void> {
  const updated = [record, ...(await getHistory())];

  // Cap the list and delete the photos of evicted records, so storage stops
  // growing once the list does rather than accumulating orphaned images.
  for (const evicted of updated.splice(MAX_HISTORY)) {
    deleteQuietly(evicted.imageUri);
  }
  await AsyncStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
}

export async function clearHistory(): Promise<void> {
  for (const record of await getHistory()) {
    deleteQuietly(record.imageUri);
  }
  await AsyncStorage.removeItem(HISTORY_KEY);
}
