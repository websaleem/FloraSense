import { useFocusEffect } from 'expo-router';
import { useCallback, useState } from 'react';
import { clearHistory, getHistory } from '../services/history';
import { ScanRecord } from '../types';

export function useHistory() {
  const [records, setRecords] = useState<ScanRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRecords(await getHistory());
    } catch (err) {
      console.error('Failed to load scan history:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Reload whenever the screen regains focus, so a scan made meanwhile shows up.
  useFocusEffect(useCallback(() => { load(); }, [load]));

  const clear = useCallback(async () => {
    await clearHistory();
    setRecords([]);
  }, []);

  return { records, loading, clear, refresh: load };
}
