import { CameraView } from 'expo-camera';
import { ImageManipulator, SaveFormat } from 'expo-image-manipulator';
import * as ImagePicker from 'expo-image-picker';
import { useRouter } from 'expo-router';
import React, { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { COLORS } from '../constants/theme';
import { useCamera } from '../hooks/useCamera';
import { deleteQuietly } from '../services/files';
import { addToHistory, saveImageLocally } from '../services/history';
import { IdentifyError, identifyFlower } from '../services/identifier';
import { ScanRecord } from '../types';

type Rect = { x: number; y: number; width: number; height: number };

function measureView(ref: React.RefObject<View | null>): Promise<Rect> {
  return new Promise(resolve => {
    ref.current?.measure((_x, _y, width, height, pageX, pageY) => {
      resolve({ x: pageX, y: pageY, width, height });
    });
  });
}

/**
 * Map the on-screen reticle onto the captured photo. The preview fills the
 * screen with "cover" scaling, so part of the photo is off-screen on one axis;
 * account for that overflow so the crop is exactly what the user framed.
 */
function computeCrop(photoW: number, photoH: number, screenW: number, screenH: number, reticle: Rect) {
  const scale = Math.max(screenW / photoW, screenH / photoH);
  const overflowX = (photoW * scale - screenW) / 2;
  const overflowY = (photoH * scale - screenH) / 2;
  const originX = Math.max(0, Math.round((reticle.x + overflowX) / scale));
  const originY = Math.max(0, Math.round((reticle.y + overflowY) / scale));
  return {
    originX,
    originY,
    width: Math.min(Math.round(reticle.width / scale), photoW - originX),
    height: Math.min(Math.round(reticle.height / scale), photoH - originY),
  };
}

export default function CameraScreen() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { permission, requestPermission, cameraRef, isCapturing, takePicture } = useCamera();
  const [isIdentifying, setIsIdentifying] = useState(false);
  const reticleRef = useRef<View>(null);
  const busy = isCapturing || isIdentifying;

  async function identifyAndShow(photoUri: string) {
    setIsIdentifying(true);
    try {
      const predictions = await identifyFlower(photoUri);
      const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const savedUri = saveImageLocally(photoUri, id);
      const record: ScanRecord = { id, timestamp: Date.now(), imageUri: savedUri, predictions };
      await addToHistory(record);
      router.push({
        pathname: '/result',
        params: { imageUri: savedUri, predictions: JSON.stringify(predictions) },
      });
    } catch (err) {
      const message = err instanceof IdentifyError
        ? err.message
        : 'Something went wrong while identifying the flower. Please try again.';
      Alert.alert('Could not identify', message);
    } finally {
      setIsIdentifying(false);
    }
  }

  async function handleCapture() {
    if (busy) return;
    const photo = await takePicture();
    if (!photo) return;

    let croppedUri: string | null = null;
    try {
      const { width: screenW, height: screenH } = Dimensions.get('window');
      const reticle = await measureView(reticleRef);
      const crop = computeCrop(photo.width, photo.height, screenW, screenH, reticle);
      const cropped = await ImageManipulator.manipulate(photo.uri).crop(crop).renderAsync();
      croppedUri = (await cropped.saveAsync({ compress: 0.9, format: SaveFormat.JPEG })).uri;
      await identifyAndShow(croppedUri);
    } finally {
      deleteQuietly(photo.uri);
      deleteQuietly(croppedUri);
    }
  }

  async function handlePickFromGallery() {
    if (busy) return;
    // Uses the system photo picker, which needs no storage permission.
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: true,
      aspect: [1, 1],
      quality: 0.9,
    });
    if (result.canceled || !result.assets?.[0]) return;
    await identifyAndShow(result.assets[0].uri);
  }

  const topBar = (
    <View style={[styles.topBar, { paddingTop: insets.top + 8 }]}>
      <Text style={styles.brand}>🌸 FloraSense</Text>
      <View style={styles.topActions}>
        <TouchableOpacity onPress={() => router.push('/history')} hitSlop={8} disabled={busy}>
          <Text style={styles.topLink}>History</Text>
        </TouchableOpacity>
        <TouchableOpacity onPress={() => router.push('/about')} hitSlop={8} disabled={busy}>
          <Text style={styles.topLink}>About</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  if (!permission) {
    return <View style={styles.fill} />;
  }

  if (!permission.granted) {
    return (
      <View style={[styles.fill, styles.permissionScreen]}>
        {topBar}
        <View style={styles.permissionBody}>
          <Text style={styles.permissionTitle}>Identify flowers with your camera</Text>
          <Text style={styles.permissionText}>
            FloraSense needs camera access to photograph a flower. Photos are sent only to identify the
            species and are never stored on our servers.
          </Text>
          <TouchableOpacity style={styles.primaryBtn} onPress={requestPermission}>
            <Text style={styles.primaryBtnText}>Allow Camera</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.secondaryBtn} onPress={handlePickFromGallery} disabled={busy}>
            <Text style={styles.secondaryBtnText}>Choose from Gallery Instead</Text>
          </TouchableOpacity>
        </View>
        {isIdentifying && <BusyOverlay />}
      </View>
    );
  }

  return (
    <View style={styles.fill}>
      <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" />

      {topBar}

      <View style={styles.reticleWrap} pointerEvents="none">
        <View ref={reticleRef} style={styles.reticle} collapsable={false} />
        <Text style={styles.hint}>Centre one flower in the frame</Text>
      </View>

      <View style={[styles.controls, { paddingBottom: insets.bottom + 24 }]}>
        <TouchableOpacity style={styles.galleryBtn} onPress={handlePickFromGallery} disabled={busy}>
          <Text style={styles.galleryText}>Gallery</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.shutter, busy && styles.shutterDisabled]}
          onPress={handleCapture}
          disabled={busy}
          accessibilityLabel="Take photo and identify"
        >
          <View style={styles.shutterInner} />
        </TouchableOpacity>
        <View style={styles.galleryBtn} />
      </View>

      {isIdentifying && <BusyOverlay />}
    </View>
  );
}

function BusyOverlay() {
  return (
    <View style={styles.overlay}>
      <ActivityIndicator size="large" color="#fff" />
      <Text style={styles.overlayText}>Identifying…</Text>
    </View>
  );
}

const RETICLE = Math.min(Dimensions.get('window').width * 0.78, 340);

const styles = StyleSheet.create({
  fill: { flex: 1, backgroundColor: '#000' },
  topBar: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 12,
    backgroundColor: 'rgba(26,16,36,0.55)',
    zIndex: 2,
  },
  brand: { color: '#fff', fontSize: 20, fontWeight: '800' },
  topActions: { flexDirection: 'row', gap: 18 },
  topLink: { color: '#fff', fontSize: 15, fontWeight: '600' },
  reticleWrap: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  reticle: {
    width: RETICLE,
    height: RETICLE,
    borderRadius: 20,
    borderWidth: 3,
    borderColor: 'rgba(255,255,255,0.9)',
  },
  hint: {
    marginTop: 14,
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
    textShadowColor: 'rgba(0,0,0,0.6)',
    textShadowRadius: 4,
  },
  controls: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-around',
    paddingTop: 20,
    backgroundColor: 'rgba(26,16,36,0.55)',
  },
  galleryBtn: { width: 80, alignItems: 'center' },
  galleryText: { color: '#fff', fontSize: 15, fontWeight: '600' },
  shutter: {
    width: 76,
    height: 76,
    borderRadius: 38,
    borderWidth: 4,
    borderColor: '#fff',
    alignItems: 'center',
    justifyContent: 'center',
  },
  shutterDisabled: { opacity: 0.4 },
  shutterInner: { width: 58, height: 58, borderRadius: 29, backgroundColor: COLORS.primary },
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.6)',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 10,
  },
  overlayText: { color: '#fff', fontSize: 17, fontWeight: '600', marginTop: 12 },
  permissionScreen: { backgroundColor: COLORS.bgLight },
  permissionBody: { flex: 1, justifyContent: 'center', padding: 28 },
  permissionTitle: { fontSize: 24, fontWeight: '800', color: COLORS.textMain, marginBottom: 12 },
  permissionText: { fontSize: 15, lineHeight: 22, color: COLORS.textMuted, marginBottom: 28 },
  primaryBtn: { backgroundColor: COLORS.primary, borderRadius: 12, paddingVertical: 16, alignItems: 'center' },
  primaryBtnText: { color: '#fff', fontWeight: '700', fontSize: 16 },
  secondaryBtn: {
    marginTop: 12,
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    borderWidth: 2,
    borderColor: COLORS.primary,
  },
  secondaryBtnText: { color: COLORS.primaryDark, fontWeight: '700', fontSize: 16 },
});
