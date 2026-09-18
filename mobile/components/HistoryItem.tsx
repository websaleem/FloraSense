import { useRouter } from 'expo-router';
import React from 'react';
import { Image, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { COLORS } from '../constants/theme';
import { ScanRecord } from '../types';
import { formatPercent, titleCase } from './PredictionResult';

type Props = {
  record: ScanRecord;
};

export function HistoryItem({ record }: Props) {
  const router = useRouter();
  const [top] = record.predictions;
  const date = new Date(record.timestamp);
  const dateStr = date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  const timeStr = date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

  function handlePress() {
    router.push({
      pathname: '/result',
      params: {
        imageUri: record.imageUri,
        predictions: JSON.stringify(record.predictions),
        readonly: '1',
      },
    });
  }

  return (
    <TouchableOpacity style={styles.row} onPress={handlePress} activeOpacity={0.75}>
      <Image source={{ uri: record.imageUri }} style={styles.thumb} />
      <View style={styles.meta}>
        <Text style={styles.name} numberOfLines={1}>{top ? titleCase(top.name) : 'Unknown'}</Text>
        <Text style={styles.date}>
          {dateStr} · {timeStr}
          {top ? ` · ${formatPercent(top.probability)}` : ''}
        </Text>
      </View>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: '#e0e0e0',
    gap: 12,
  },
  thumb: {
    width: 64,
    height: 64,
    borderRadius: 10,
    backgroundColor: '#eee',
  },
  meta: {
    flex: 1,
  },
  name: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.textMain,
    marginBottom: 3,
  },
  date: {
    fontSize: 12,
    color: COLORS.textMuted,
  },
});
