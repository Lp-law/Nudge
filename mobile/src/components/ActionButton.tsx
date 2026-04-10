import React from "react";
import {
  StyleSheet,
  Text,
  TouchableOpacity,
  ViewStyle,
} from "react-native";

interface ActionButtonProps {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  style?: ViewStyle;
}

/**
 * Reusable action button used for each AI action on the HomeScreen.
 * Styled to match the dark Nudge theme (#121826 background).
 */
export default function ActionButton({
  label,
  onPress,
  disabled = false,
  style,
}: ActionButtonProps) {
  return (
    <TouchableOpacity
      style={[styles.button, disabled && styles.disabled, style]}
      onPress={onPress}
      disabled={disabled}
      activeOpacity={0.7}
    >
      <Text style={[styles.label, disabled && styles.disabledLabel]}>
        {label}
      </Text>
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  button: {
    backgroundColor: "#1E2A42",
    borderRadius: 9,
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: "center",
    justifyContent: "center",
    borderWidth: 1,
    borderColor: "#2E3A56",
  },
  disabled: {
    opacity: 0.4,
  },
  label: {
    color: "#E8EEFF",
    fontSize: 14,
    fontWeight: "600",
    textAlign: "center",
  },
  disabledLabel: {
    color: "#8899BB",
  },
});
