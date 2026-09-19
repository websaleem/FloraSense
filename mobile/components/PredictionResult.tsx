import React from 'react';
import { StyleSheet, Text, View } from 'react-native';
import { COLORS } from '../constants/theme';
import { Prediction } from '../types';

export function titleCase(name: string): string {
  return name.replace(/\b\w/g, c => c.toUpperCase());
}

export function formatPercent(probability: number): string {
  return `${(probability * 100).toFixed(1)}%`;
}

type Props = {
  predictions: Prediction[];
};

export function PredictionResult({ predictions }: Props) {
  const [top] = predictions;
  if (!top) return null;

  return (
    <View style={styles.card}>
      <Text style={styles.label}>MOST LIKELY SPECIES</Text>
      <Text style={styles.topName}>{titleCase(top.name)}</Text>
      <Text style={styles.topConfidence}>{formatPercent(top.probability)} confidence</Text>

      <View style={styles.divider} />

      {predictions.map((p, i) => (
        <View key={`${p.classId}-${i}`} style={styles.row}>
          <View style={styles.rank}>
            <Text style={styles.rankText}>{i + 1}</Text>
          </View>
          <View style={styles.info}>
            <Text style={styles.name} numberOfLines={1}>{titleCase(p.name)}</Text>
            <View style={styles.track}>
              <View style={[styles.fill, { width: `${Math.max(1, p.probability * 100)}%` }]} />
            </View>
          </View>
          <Text style={styles.prob}>{formatPercent(p.probability)}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    width: '88%',
    backgroundColor: COLORS.bgWhite,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 20,
    marginTop: 12,
  },
  label: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1.2,
    color: COLORS.textMuted,
  },
  topName: {
    fontSize: 26,
    fontWeight: '800',
    color: COLORS.primaryDark,
    marginTop: 4,
  },
  topConfidence: {
    fontSize: 14,
    color: COLORS.textMuted,
    marginTop: 2,
  },
  divider: {
    height: StyleSheet.hairlineWidth,
    backgroundColor: COLORS.border,
    marginVertical: 14,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 6,
    gap: 10,
  },
  rank: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: COLORS.primaryLight,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rankText: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.primaryDark,
  },
  info: {
    flex: 1,
  },
  name: {
    fontSize: 14,
    fontWeight: '600',
    color: COLORS.textMain,
    marginBottom: 4,
  },
  track: {
    height: 6,
    borderRadius: 3,
    backgroundColor: '#f1e8f8',
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    borderRadius: 3,
    backgroundColor: COLORS.primary,
  },
  prob: {
    width: 52,
    textAlign: 'right',
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.textMuted,
  },
});
