import React from "react";
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import Constants from "expo-constants";
import { useAuth } from "../hooks/useAuth";
import he from "../i18n/he";

export default function SettingsScreen() {
  const { logout } = useAuth();

  const handleLogout = () => {
    Alert.alert(he.logoutConfirm, "", [
      { text: he.cancel, style: "cancel" },
      {
        text: he.logoutConfirmYes,
        style: "destructive",
        onPress: async () => {
          await logout();
        },
      },
    ]);
  };

  const version = Constants.expoConfig?.version ?? "1.0.0";

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      {/* About section */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>{he.about}</Text>

        <View style={styles.row}>
          <Text style={styles.rowLabel}>{he.settingsVersion}</Text>
          <Text style={styles.rowValue}>{version}</Text>
        </View>

        <View style={styles.row}>
          <Text style={styles.rowLabel}>{he.settingsBuildInfo}</Text>
          <Text style={styles.rowValue}>
            Expo SDK {Constants.expoConfig?.sdkVersion ?? "52"}
          </Text>
        </View>
      </View>

      {/* Logout */}
      <View style={styles.section}>
        <TouchableOpacity
          style={styles.logoutButton}
          onPress={handleLogout}
          activeOpacity={0.7}
        >
          <Text style={styles.logoutButtonText}>{he.logout}</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#121826",
  },
  content: {
    padding: 20,
  },
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    color: "#8899BB",
    fontSize: 13,
    fontWeight: "600",
    marginBottom: 10,
    writingDirection: "rtl",
  },
  row: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    backgroundColor: "#1A2236",
    borderRadius: 10,
    padding: 14,
    marginBottom: 8,
    borderWidth: 1,
    borderColor: "#2E3A56",
  },
  rowLabel: {
    color: "#C0CCEE",
    fontSize: 14,
  },
  rowValue: {
    color: "#8899BB",
    fontSize: 14,
  },
  logoutButton: {
    backgroundColor: "#3D1520",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#6B2030",
  },
  logoutButtonText: {
    color: "#FF6B7A",
    fontSize: 15,
    fontWeight: "600",
  },
});
