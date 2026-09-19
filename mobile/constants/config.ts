const rawBase = (process.env.EXPO_PUBLIC_API_BASE_URL ?? '').replace(/\/$/, '');
if (!rawBase) {
  throw new Error('EXPO_PUBLIC_API_BASE_URL is not configured');
}
if (!rawBase.startsWith('https://')) {
  throw new Error('EXPO_PUBLIC_API_BASE_URL must be an https URL');
}

export const API_BASE = rawBase;

/** Number of ranked candidates to request. The API accepts 1–102. */
export const TOP_K = 5;

/** Longest edge sent to the API, matching what the website sends. */
export const MAX_IMAGE_PX = 1024;

/** Oldest scans beyond this are pruned, along with their saved photos. */
export const MAX_HISTORY = 50;

export const SITE_URL = 'https://florasense.websaleem.com';
export const PRIVACY_URL = `${SITE_URL}/privacy.html`;
export const TERMS_URL = `${SITE_URL}/terms.html`;
export const SUPPORT_URL = `${SITE_URL}/contact-support.html`;
