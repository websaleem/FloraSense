import { useLocalSearchParams, useRouter } from 'expo-router';
import React, { useMemo } from 'react';
import { Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { PredictionResult } from '../components/PredictionResult';
import { COLORS } from '../constants/theme';
import { isHistoryImage } from '../services/history';
import { Prediction } from '../types';

/** Route params are strings from anywhere a deep link can reach; parse defensively. */
function parsePredictions(raw: string | undefined): Prediction[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter(p => p && typeof p.name === 'string' && typeof p.probability === 'number')
      .slice(0, 102)
      .map(p => ({ classId: String(p.classId ?? ''), name: p.name, probability: p.probability }));
  } catch {
    return [];
  }
}

export default function ResultScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ imageUri?: string; predictions?: string; readonly?: string }>();

  const predictions = useMemo(() => parsePredictions(params.predictions), [params.predictions]);
  const imageUri = isHistoryImage(params.imageUri) ? params.imageUri : undefined;
  const isReadonly = params.readonly === '1';

  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      {imageUri ? (
        <View style={styles.imageFrame}>
          <Image source={{ uri: imageUri }} style={styles.image} resizeMode="cover" />
        </View>
      ) : null}

      {predictions.length > 0 ? (
        <PredictionResult predictions={predictions} />
      ) : (
        <Text style={styles.empty}>No result to show.</Text>
      )}

      <View style={styles.warning}>
        <Text style={styles.warningTitle}>⚠ Identification is not advice</Text>
        <Text style={styles.warningText}>
          FloraSense is wrong roughly one time in seven and only knows 102 flower categories. Never use it to
          decide whether a plant is safe to eat, touch, or give to a person or animal.
        </Text>
      </View>

      {!isReadonly && (
        <TouchableOpacity style={styles.againBtn} onPress={() => router.back()}>
          <Text style={styles.againText}>Identify Another Flower</Text>
        </TouchableOpacity>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: COLORS.bgLight },
  content: { paddingBottom: 40, alignItems: 'center' },
  imageFrame: {
    width: '88%',
    aspectRatio: 1,
    borderRadius: 16,
    overflow: 'hidden',
    marginTop: 20,
    backgroundColor: '#eee',
    borderWidth: 2,
    borderColor: '#fff',
    elevation: 4,
  },
  image: { width: '100%', height: '100%' },
  empty: { marginTop: 40, color: COLORS.textMuted, fontSize: 16 },
  warning: {
    width: '88%',
    marginTop: 14,
    padding: 14,
    borderRadius: 12,
    backgroundColor: COLORS.warnBg,
    borderWidth: 1,
    borderColor: COLORS.warnBorder,
  },
  warningTitle: { fontSize: 14, fontWeight: '700', color: '#b45309', marginBottom: 4 },
  warningText: { fontSize: 13, lineHeight: 19, color: COLORS.warnText },
  againBtn: {
    width: '88%',
    marginTop: 14,
    paddingVertical: 16,
    borderRadius: 12,
    backgroundColor: COLORS.primary,
    alignItems: 'center',
  },
  againText: { color: '#fff', fontWeight: '700', fontSize: 16 },
});
