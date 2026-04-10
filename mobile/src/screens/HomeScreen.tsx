import React, { useState } from "react";
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import type { NativeStackNavigationProp } from "@react-navigation/native-stack";
import { useNavigation } from "@react-navigation/native";
import type { ActionType } from "../api/ai";
import { useAIAction } from "../hooks/useAIAction";
import ActionButton from "../components/ActionButton";
import TextInputArea from "../components/TextInputArea";
import LoadingOverlay from "../components/LoadingOverlay";
import { convertEnLayoutToHebrew } from "../utils/clipboard";
import he from "../i18n/he";
import type { RootStackParamList } from "../../App";

// Grid layout matching the desktop popup (action_contract.py TEXT_ACTION_GRID_ROWS).
const ACTION_GRID: { key: ActionType | "fix_layout_he"; label: string }[][] = [
  [
    { key: "summarize", label: he.action_summarize },
    { key: "improve", label: he.action_improve },
  ],
  [
    { key: "make_email", label: he.action_make_email },
    { key: "reply_email", label: he.action_reply_email },
  ],
  [
    { key: "fix_language", label: he.action_fix_language },
    { key: "translate_to_he", label: he.action_translate_to_he },
  ],
  [
    { key: "translate_to_en", label: he.action_translate_to_en },
    { key: "fix_layout_he", label: he.action_fix_layout_he },
  ],
  [{ key: "explain_meaning", label: he.action_explain_meaning }],
];

type HomeNav = NativeStackNavigationProp<RootStackParamList, "Home">;

export default function HomeScreen() {
  const navigation = useNavigation<HomeNav>();
  const [text, setText] = useState("");
  const { isLoading, execute } = useAIAction();

  const handleAction = async (actionKey: ActionType | "fix_layout_he") => {
    const trimmed = text.trim();
    if (!trimmed) {
      Alert.alert(he.error, he.errorInvalidText);
      return;
    }

    // fix_layout_he is a local-only action (no server call).
    if (actionKey === "fix_layout_he") {
      const converted = convertEnLayoutToHebrew(trimmed);
      navigation.navigate("Result", { result: converted });
      return;
    }

    try {
      await execute(actionKey, trimmed);
    } catch {
      // Error is handled inside the hook, but just in case.
    }
  };

  // Navigate to result when the hook produces one.
  // We use a simple React effect approach via onPress callback.
  const handleActionPress = async (
    actionKey: ActionType | "fix_layout_he",
  ) => {
    if (actionKey === "fix_layout_he") {
      handleAction(actionKey);
      return;
    }

    const trimmed = text.trim();
    if (!trimmed) {
      Alert.alert(he.error, he.errorInvalidText);
      return;
    }

    try {
      // Inline the action call so we can navigate on success.
      const { runAction } = await import("../api/ai");
      const result = await runAction(actionKey, trimmed);
      navigation.navigate("Result", { result });
    } catch (err: unknown) {
      Alert.alert(
        he.error,
        err instanceof Error ? err.message : he.errorRequestFailed,
      );
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        <TextInputArea
          value={text}
          onChangeText={setText}
          placeholder={he.homeInputPlaceholder}
          editable={!isLoading}
        />

        <Text style={styles.sectionTitle}>{he.homeSelectAction}</Text>

        {ACTION_GRID.map((row, rowIdx) => (
          <View key={rowIdx} style={styles.row}>
            {row.map(({ key, label }) => (
              <ActionButton
                key={key}
                label={label}
                onPress={() => handleActionPress(key)}
                disabled={isLoading}
                style={styles.gridButton}
              />
            ))}
          </View>
        ))}

        {/* OCR shortcut */}
        <TouchableOpacity
          style={styles.ocrButton}
          onPress={() => navigation.navigate("OCR")}
          disabled={isLoading}
          activeOpacity={0.7}
        >
          <Text style={styles.ocrButtonText}>{he.ocrTitle}</Text>
        </TouchableOpacity>
      </ScrollView>

      <LoadingOverlay visible={isLoading} />
    </View>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: "#121826",
  },
  scroll: {
    flex: 1,
  },
  scrollContent: {
    padding: 16,
    paddingBottom: 40,
  },
  sectionTitle: {
    color: "#8899BB",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 20,
    marginBottom: 10,
    writingDirection: "rtl",
  },
  row: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 10,
  },
  gridButton: {
    flex: 1,
  },
  ocrButton: {
    backgroundColor: "#2E3A56",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 12,
  },
  ocrButtonText: {
    color: "#C0CCEE",
    fontSize: 14,
    fontWeight: "600",
  },
});
