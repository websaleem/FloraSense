import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { COLORS } from '../constants/theme';

export default function RootLayout() {
  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: COLORS.primaryDark },
          headerTintColor: '#fff',
          headerTitleStyle: { fontWeight: 'bold' },
          contentStyle: { backgroundColor: COLORS.bgLight },
        }}
      >
        <Stack.Screen name="index" options={{ title: 'FloraSense', headerShown: false }} />
        <Stack.Screen name="result" options={{ title: 'Result', presentation: 'modal' }} />
        <Stack.Screen name="history" options={{ title: 'Scan History' }} />
        <Stack.Screen name="about" options={{ title: 'About FloraSense' }} />
      </Stack>
    </>
  );
}
