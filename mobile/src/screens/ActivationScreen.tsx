import React, { useState } from "react";
import {
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { useAuth } from "../hooks/useAuth";
import LoadingOverlay from "../components/LoadingOverlay";
import he from "../i18n/he";

/**
 * First screen shown when the user has not yet activated.
 * Accepts a license key and exchanges it for auth tokens via POST /auth/activate.
 */
export default function ActivationScreen() {
  const { activate } = useAuth();
  const [licenseKey, setLicenseKey] = useState("");
  const [loading, setLoading] = useState(false);

  const handleActivate = async () => {
    const trimmed = licenseKey.trim();
    if (trimmed.length < 8) {
      Alert.alert(he.error, he.activationErrorEmpty);
      return;
    }

    setLoading(true);
    try {
      await activate(trimmed);
      // On success AuthContext flips isAuthenticated -> navigation switches automatically.
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : he.activationFailedGeneric;
      Alert.alert(he.error, message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === "ios" ? "padding" : undefined}
    >
      <ScrollView
        contentContainerStyle={styles.scroll}
        keyboardShouldPersistTaps="handled"
      >
        <View style={styles.card}>
          <Text style={styles.title}>{he.activationTitle}</Text>
          <Text style={styles.subtitle}>{he.activationSubtitle}</Text>

          <Text style={styles.label}>{he.activationLicenseLabel}</Text>
          <TextInput
            style={styles.input}
            value={licenseKey}
            onChangeText={setLicenseKey}
            placeholder="XXXX-XXXX-XXXX-XXXX"
            placeholderTextColor="#5A6B8A"
            autoCapitalize="none"
            autoCorrect={false}
            editable={!loading}
          />

          <TouchableOpacity
            style={[styles.button, loading && styles.buttonDisabled]}
            onPress={handleActivate}
            disabled={loading}
            activeOpacity={0.7}
          >
            <Text style={styles.buttonText}>{he.activationSubmit}</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>

      <LoadingOverlay visible={loading} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#121826",
  },
  scroll: {
    flexGrow: 1,
    justifyContent: "center",
    padding: 24,
  },
  card: {
    backgroundColor: "#1A2236",
    borderRadius: 16,
    padding: 24,
    borderWidth: 1,
    borderColor: "#2E3A56",
  },
  title: {
    color: "#E8EEFF",
    fontSize: 22,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 8,
  },
  subtitle: {
    color: "#8899BB",
    fontSize: 14,
    textAlign: "center",
    lineHeight: 20,
    marginBottom: 24,
    writingDirection: "rtl",
  },
  label: {
    color: "#C0CCEE",
    fontSize: 13,
    marginBottom: 6,
    writingDirection: "rtl",
  },
  input: {
    backgroundColor: "#0D1320",
    borderWidth: 1,
    borderColor: "#2E3A56",
    borderRadius: 10,
    color: "#E8EEFF",
    fontSize: 15,
    paddingHorizontal: 14,
    paddingVertical: 12,
    marginBottom: 20,
    textAlign: "left",
  },
  button: {
    backgroundColor: "#4C6EF5",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.5,
  },
  buttonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "600",
  },
});
