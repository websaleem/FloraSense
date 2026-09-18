import React from 'react';
import { Linking, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { PRIVACY_URL, SUPPORT_URL, TERMS_URL } from '../constants/config';
import { COLORS } from '../constants/theme';

const MODELS = [
  { arch: 'EfficientNet-B0', accuracy: '86.57%', correct: '709 / 819', live: true },
  { arch: 'DenseNet-121', accuracy: '83.15%', correct: '681 / 819', live: false },
  { arch: 'VGG-16', accuracy: '77.53%', correct: '635 / 819', live: false },
];

function LinkRow({ label, url }: { label: string; url: string }) {
  return (
    <TouchableOpacity style={styles.linkRow} onPress={() => Linking.openURL(url)} activeOpacity={0.7}>
      <Text style={styles.linkText}>{label}</Text>
      <Text style={styles.linkArrow}>›</Text>
    </TouchableOpacity>
  );
}

export default function AboutScreen() {
  return (
    <ScrollView style={styles.scroll} contentContainerStyle={styles.content}>
      <Text style={styles.h1}>🌸 FloraSense</Text>
      <Text style={styles.body}>
        FloraSense identifies flower species from a photo using a deep learning model trained on 102 flower
        categories. It returns the five closest matches with a confidence score for each.
      </Text>

      <Text style={styles.h2}>How your photo is handled</Text>
      <Text style={styles.body}>
        The photo is resized on your phone, sent over HTTPS, classified, and deleted from the server before the
        answer comes back. It is never stored, reviewed, or used for training. Your history stays on this device.
      </Text>

      <Text style={styles.h2}>Model accuracy</Text>
      <View style={styles.table}>
        {MODELS.map(m => (
          <View key={m.arch} style={styles.tableRow}>
            <Text style={styles.arch}>
              {m.arch}
              {m.live ? <Text style={styles.live}>  LIVE</Text> : null}
            </Text>
            <Text style={styles.cell}>{m.accuracy}</Text>
          </View>
        ))}
      </View>
      <Text style={styles.note}>Top-1 accuracy on 819 held-out test images.</Text>

      <Text style={styles.h2}>Legal & support</Text>
      <View style={styles.links}>
        <LinkRow label="Privacy Policy" url={PRIVACY_URL} />
        <LinkRow label="Terms of Service" url={TERMS_URL} />
        <LinkRow label="Contact Support" url={SUPPORT_URL} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  scroll: { flex: 1, backgroundColor: COLORS.bgLight },
  content: { padding: 22, paddingBottom: 48 },
  h1: { fontSize: 26, fontWeight: '800', color: COLORS.primaryDark, marginBottom: 10 },
  h2: { fontSize: 17, fontWeight: '700', color: COLORS.textMain, marginTop: 24, marginBottom: 8 },
  body: { fontSize: 15, lineHeight: 22, color: COLORS.textMuted },
  table: { backgroundColor: '#fff', borderRadius: 12, borderWidth: 1, borderColor: '#e2e8f0', overflow: 'hidden' },
  tableRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    paddingVertical: 12,
    paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e2e8f0',
  },
  arch: { fontSize: 15, fontWeight: '700', color: COLORS.textMain },
  live: { fontSize: 11, fontWeight: '800', color: COLORS.primary },
  cell: { fontSize: 15, color: COLORS.textMain },
  note: { fontSize: 12, color: COLORS.textMuted, marginTop: 8 },
  links: { backgroundColor: '#fff', borderRadius: 12, borderWidth: 1, borderColor: '#e2e8f0', overflow: 'hidden' },
  linkRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 14,
    paddingHorizontal: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e2e8f0',
  },
  linkText: { fontSize: 15, fontWeight: '600', color: COLORS.primaryDark },
  linkArrow: { fontSize: 20, color: COLORS.textMuted },
});
