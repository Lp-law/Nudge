import React from "react";
import {
  ActivityIndicator,
  Modal,
  StyleSheet,
  Text,
  View,
} from "react-native";
import he from "../i18n/he";

interface LoadingOverlayProps {
  visible: boolean;
  message?: string;
}

/**
 * Full-screen semi-transparent loading overlay with a spinner.
 */
export default function LoadingOverlay({
  visible,
  message,
}: LoadingOverlayProps) {
  if (!visible) return null;

  return (
    <Modal transparent animationType="fade" visible={visible}>
      <View style={styles.backdrop}>
        <View style={styles.card}>
          <ActivityIndicator size="large" color="#6C8EEF" />
          <Text style={styles.text}>{message ?? he.loading}</Text>
        </View>
      </View>
    </Modal>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: "rgba(0,0,0,0.55)",
    justifyContent: "center",
    alignItems: "center",
  },
  card: {
    backgroundColor: "#1E2A42",
    borderRadius: 16,
    padding: 32,
    alignItems: "center",
    gap: 16,
  },
  text: {
    color: "#E8EEFF",
    fontSize: 15,
    marginTop: 8,
  },
});
