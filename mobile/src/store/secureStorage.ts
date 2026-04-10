import * as SecureStore from "expo-secure-store";

const KEYS = {
  accessToken: "nudge_access_token",
  refreshToken: "nudge_refresh_token",
  expiresAt: "nudge_token_expires_at",
  refreshExpiresAt: "nudge_refresh_expires_at",
  deviceId: "nudge_device_id",
} as const;

// ---- Access token ----

export async function getAccessToken(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.accessToken);
}

export async function getRefreshToken(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.refreshToken);
}

export async function getTokenExpiresAt(): Promise<number | null> {
  const raw = await SecureStore.getItemAsync(KEYS.expiresAt);
  return raw ? Number(raw) : null;
}

export async function getRefreshExpiresAt(): Promise<number | null> {
  const raw = await SecureStore.getItemAsync(KEYS.refreshExpiresAt);
  return raw ? Number(raw) : null;
}

export async function storeTokens(
  accessToken: string,
  refreshToken: string,
  expiresIn: number,
  refreshExpiresIn: number,
): Promise<void> {
  const now = Date.now();
  await Promise.all([
    SecureStore.setItemAsync(KEYS.accessToken, accessToken),
    SecureStore.setItemAsync(KEYS.refreshToken, refreshToken),
    SecureStore.setItemAsync(
      KEYS.expiresAt,
      String(now + expiresIn * 1000),
    ),
    SecureStore.setItemAsync(
      KEYS.refreshExpiresAt,
      String(now + refreshExpiresIn * 1000),
    ),
  ]);
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(KEYS.accessToken),
    SecureStore.deleteItemAsync(KEYS.refreshToken),
    SecureStore.deleteItemAsync(KEYS.expiresAt),
    SecureStore.deleteItemAsync(KEYS.refreshExpiresAt),
  ]);
}

// ---- Device ID ----

export async function getDeviceId(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.deviceId);
}

export async function storeDeviceId(id: string): Promise<void> {
  await SecureStore.setItemAsync(KEYS.deviceId, id);
}
