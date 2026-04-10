import React from "react";
import { StyleSheet, TextInput, View } from "react-native";

interface TextInputAreaProps {
  value: string;
  onChangeText: (text: string) => void;
  placeholder?: string;
  editable?: boolean;
}

/**
 * Multi-line text input styled for the Nudge dark theme.
 * Used on HomeScreen for entering text before running an action.
 */
export default function TextInputArea({
  value,
  onChangeText,
  placeholder,
  editable = true,
}: TextInputAreaProps) {
  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#5A6B8A"
        multiline
        textAlignVertical="top"
        editable={editable}
        writingDirection="auto"
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    borderWidth: 1,
    borderColor: "#2E3A56",
    borderRadius: 12,
    backgroundColor: "#0D1320",
    minHeight: 140,
    maxHeight: 300,
  },
  input: {
    color: "#E8EEFF",
    fontSize: 15,
    lineHeight: 22,
    padding: 14,
    flex: 1,
  },
});
