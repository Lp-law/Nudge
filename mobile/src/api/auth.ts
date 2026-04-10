import apiClient from "./client";
import { API_ENDPOINTS } from "../config";

// ---- Request / Response types matching the FastAPI backend ----

export interface ActivateRequest {
  license_key: string;
  device_id: string;
}

export interface RefreshRequest {
  refresh_token: string;
}

export interface RevokeRequest {
  token: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
}

// ---- API calls ----

export async function activate(
  licenseKey: string,
  deviceId: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>(
    API_ENDPOINTS.activate,
    { license_key: licenseKey, device_id: deviceId } satisfies ActivateRequest,
  );
  return data;
}

export async function refresh(
  refreshToken: string,
): Promise<TokenResponse> {
  const { data } = await apiClient.post<TokenResponse>(
    API_ENDPOINTS.refresh,
    { refresh_token: refreshToken } satisfies RefreshRequest,
  );
  return data;
}

export async function revoke(token: string): Promise<void> {
  await apiClient.post(API_ENDPOINTS.revoke, {
    token,
  } satisfies RevokeRequest);
}
