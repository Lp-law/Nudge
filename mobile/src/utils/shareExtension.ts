import { Linking, Platform } from "react-native";

/**
 * Share Sheet / Intent handling utilities.
 *
 * ## Android
 * Android share intents (ACTION_SEND with text/plain) are configured in
 * app.json under android.intentFilters. When the app receives shared text,
 * it arrives via the initial URL on launch or via a Linking event.
 *
 * ## iOS
 * iOS Share Extensions require a native extension target that cannot be
 * fully configured through Expo alone. To add an iOS Share Extension:
 *
 * 1. Run `npx expo prebuild` to generate the native projects.
 * 2. Open the ios/ folder in Xcode.
 * 3. Add a new "Share Extension" target.
 * 4. In the extension's ShareViewController, extract the shared text and
 *    forward it to the main app via an App Group / URL scheme.
 * 5. Add the app group entitlement to both the main app and the extension.
 *
 * This module provides helpers for reading the shared text once it reaches
 * the React Native layer.
 */

/**
 * Extract shared text from the initial URL (Android ACTION_SEND intent).
 *
 * Call this once on app mount to check if the app was launched via a share.
 * Returns the shared text or null.
 */
export async function getInitialSharedText(): Promise<string | null> {
  try {
    const url = await Linking.getInitialURL();
    if (!url) return null;
    return parseSharedText(url);
  } catch {
    return null;
  }
}

/**
 * Subscribe to incoming share intents while the app is running.
 *
 * Returns an unsubscribe function.
 */
export function onSharedText(
  callback: (text: string) => void,
): () => void {
  const handler = ({ url }: { url: string }) => {
    const text = parseSharedText(url);
    if (text) callback(text);
  };

  const subscription = Linking.addEventListener("url", handler);
  return () => subscription.remove();
}

/**
 * Parse shared text from a URL.
 *
 * Android sends ACTION_SEND intents with the shared text in the
 * EXTRA_TEXT field, which Expo surfaces as the URL.
 * Adjust this function if you use a custom URL scheme.
 */
function parseSharedText(url: string): string | null {
  if (!url) return null;

  // On Android, shared plain text may come directly as the URL content.
  // On iOS with a custom URL scheme, it would be: nudge://share?text=...
  if (Platform.OS === "ios") {
    try {
      const parsed = new URL(url);
      const text = parsed.searchParams.get("text");
      return text || null;
    } catch {
      return null;
    }
  }

  // Android: the URL itself may be the shared text.
  return url;
}
