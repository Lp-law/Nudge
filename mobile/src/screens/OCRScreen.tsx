import React, { useState } from "react";
import {
  Alert,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import * as ImagePicker from "expo-image-picker";
import * as Clipboard from "expo-clipboard";
import * as FileSystem from "expo-file-system";
import { runOCR } from "../api/ai";
import LoadingOverlay from "../components/LoadingOverlay";
import he from "../i18n/he";

export default function OCRScreen() {
  const [imageUri, setImageUri] = useState<string | null>(null);
  const [ocrResult, setOcrResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const pickImage = async (fromCamera: boolean) => {
    const picker = fromCamera
      ? ImagePicker.launchCameraAsync
      : ImagePicker.launchImageLibraryAsync;

    const result = await picker({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
      base64: false,
    });

    if (!result.canceled && result.assets?.[0]) {
      setImageUri(result.assets[0].uri);
      setOcrResult(null);
    }
  };

  const handleExtract = async () => {
    if (!imageUri) {
      Alert.alert(he.error, he.ocrNoImage);
      return;
    }

    setLoading(true);
    try {
      // Read the file and convert to base64.
      const base64 = await FileSystem.readAsStringAsync(imageUri, {
        encoding: FileSystem.EncodingType.Base64,
      });

      const text = await runOCR(base64);
      setOcrResult(text);
    } catch (err: unknown) {
      Alert.alert(
        he.error,
        err instanceof Error ? err.message : he.errorOcrFailed,
      );
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = async () => {
    if (ocrResult) {
      await Clipboard.setStringAsync(ocrResult);
      Alert.alert(he.copied, he.resultCopied);
    }
  };

  return (
    <View style={styles.root}>
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.scrollContent}
        keyboardShouldPersistTaps="handled"
      >
        {/* Image picker buttons */}
        <View style={styles.pickerRow}>
          <TouchableOpacity
            style={styles.pickerButton}
            onPress={() => pickImage(true)}
            disabled={loading}
            activeOpacity={0.7}
          >
            <Text style={styles.pickerButtonText}>{he.ocrPickCamera}</Text>
          </TouchableOpacity>

          <TouchableOpacity
            style={styles.pickerButton}
            onPress={() => pickImage(false)}
            disabled={loading}
            activeOpacity={0.7}
          >
            <Text style={styles.pickerButtonText}>{he.ocrPickGallery}</Text>
          </TouchableOpacity>
        </View>

        {/* Image preview */}
        {imageUri && (
          <Image
            source={{ uri: imageUri }}
            style={styles.preview}
            resizeMode="contain"
          />
        )}

        {/* Extract button */}
        {imageUri && !ocrResult && (
          <TouchableOpacity
            style={styles.extractButton}
            onPress={handleExtract}
            disabled={loading}
            activeOpacity={0.7}
          >
            <Text style={styles.extractButtonText}>
              {he.ocrExtractButton}
            </Text>
          </TouchableOpacity>
        )}

        {/* OCR result */}
        {ocrResult && (
          <View style={styles.resultContainer}>
            <Text style={styles.resultText} selectable>
              {ocrResult}
            </Text>
            <TouchableOpacity
              style={styles.copyButton}
              onPress={handleCopy}
              activeOpacity={0.7}
            >
              <Text style={styles.copyButtonText}>{he.copy}</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>

      <LoadingOverlay visible={loading} message={he.ocrProcessing} />
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
  pickerRow: {
    flexDirection: "row",
    gap: 10,
    marginBottom: 16,
  },
  pickerButton: {
    flex: 1,
    backgroundColor: "#1E2A42",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: "#2E3A56",
  },
  pickerButtonText: {
    color: "#C0CCEE",
    fontSize: 14,
    fontWeight: "600",
  },
  preview: {
    width: "100%",
    height: 250,
    borderRadius: 12,
    backgroundColor: "#0D1320",
    marginBottom: 16,
  },
  extractButton: {
    backgroundColor: "#4C6EF5",
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    marginBottom: 16,
  },
  extractButtonText: {
    color: "#FFFFFF",
    fontSize: 16,
    fontWeight: "600",
  },
  resultContainer: {
    backgroundColor: "#0D1320",
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    borderColor: "#2E3A56",
  },
  resultText: {
    color: "#E8EEFF",
    fontSize: 15,
    lineHeight: 22,
    writingDirection: "auto",
    marginBottom: 12,
  },
  copyButton: {
    backgroundColor: "#4C6EF5",
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: "center",
  },
  copyButtonText: {
    color: "#FFFFFF",
    fontSize: 15,
    fontWeight: "600",
  },
});
