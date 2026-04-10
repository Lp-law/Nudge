import React from "react";
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import * as Clipboard from "expo-clipboard";
import type { NativeStackScreenProps } from "@react-navigation/native-stack";
import type { RootStackParamList } from "../../App";
import he from "../i18n/he";

type Props = NativeStackScreenProps<RootStackParamList, "Result">;

export default function ResultScreen({ route }: Props) {
  const { result } = route.params;

  const handleCopy = async () => {
    await Clipboard.setStringAsync(result);
    Alert.alert(he.copied, he.resultCopied);
  };

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
      >
        <Text style={styles.resultText} selectable>
          {result || he.resultEmpty}
        </Text>
      </ScrollView>

      <View style={styles.footer}>
        <TouchableOpacity
          style={styles.copyButton}
          onPress={handleCopy}
          activeOpacity={0.7}
        >
          <Text style={styles.copyButtonText}>{he.copy}</Text>
        </TouchableOpacity>
      </View>
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
    padding: 20,
  },
  resultText: {
    color: "#E8EEFF",
    fontSize: 16,
    lineHeight: 24,
    writingDirection: "auto",
  },
  footer: {
    padding: 16,
    borderTopWidth: 1,
    borderTopColor: "#2E3A56",
  },
  copyButton: {
    backgroundColor: "#4C6EF5",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
  },
  copyButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "600",
  },
});
