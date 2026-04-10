import React, { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, View } from "react-native";
import { NavigationContainer } from "@react-navigation/native";
import { createNativeStackNavigator } from "@react-navigation/native-stack";
import { StatusBar } from "expo-status-bar";

import { AuthProvider } from "./src/store/AuthContext";
import { useAuth } from "./src/hooks/useAuth";
import { getInitialSharedText, onSharedText } from "./src/utils/shareExtension";

import ActivationScreen from "./src/screens/ActivationScreen";
import HomeScreen from "./src/screens/HomeScreen";
import ResultScreen from "./src/screens/ResultScreen";
import OCRScreen from "./src/screens/OCRScreen";
import SettingsScreen from "./src/screens/SettingsScreen";

import he from "./src/i18n/he";

// ---- Navigation types ----

export type RootStackParamList = {
  Activation: undefined;
  Home: undefined;
  Result: { result: string };
  OCR: undefined;
  Settings: undefined;
};

const Stack = createNativeStackNavigator<RootStackParamList>();

// ---- Theme-aware header options ----

const SCREEN_OPTIONS = {
  headerStyle: { backgroundColor: "#121826" },
  headerTintColor: "#E8EEFF",
  headerTitleStyle: { fontWeight: "600" as const },
  contentStyle: { backgroundColor: "#121826" },
} as const;

// ---- Main navigator that switches based on auth state ----

function AppNavigator() {
  const { isLoading, isAuthenticated } = useAuth();

  if (isLoading) {
    return (
      <View style={styles.loadingContainer}>
        <ActivityIndicator size="large" color="#6C8EEF" />
      </View>
    );
  }

  return (
    <Stack.Navigator screenOptions={SCREEN_OPTIONS}>
      {!isAuthenticated ? (
        <Stack.Screen
          name="Activation"
          component={ActivationScreen}
          options={{ headerShown: false }}
        />
      ) : (
        <>
          <Stack.Screen
            name="Home"
            component={HomeScreen}
            options={{
              title: he.homeTitle,
              headerRight: () => null, // Settings icon added below via navigation
            }}
          />
          <Stack.Screen
            name="Result"
            component={ResultScreen}
            options={{ title: he.resultTitle }}
          />
          <Stack.Screen
            name="OCR"
            component={OCRScreen}
            options={{ title: he.ocrTitle }}
          />
          <Stack.Screen
            name="Settings"
            component={SettingsScreen}
            options={{ title: he.settingsTitle }}
          />
        </>
      )}
    </Stack.Navigator>
  );
}

// ---- Root App component ----

export default function App() {
  return (
    <AuthProvider>
      <NavigationContainer>
        <StatusBar style="light" />
        <AppNavigator />
      </NavigationContainer>
    </AuthProvider>
  );
}

const styles = StyleSheet.create({
  loadingContainer: {
    flex: 1,
    backgroundColor: "#121826",
    justifyContent: "center",
    alignItems: "center",
  },
});
