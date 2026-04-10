/**
 * Backend API configuration.
 *
 * For local development, change BACKEND_URL to your machine's IP
 * (e.g. "http://192.168.1.100:8000") since "localhost" from a
 * device/emulator refers to the device itself, not the host machine.
 */

export const BACKEND_URL = "https://api.nudge.example.com";

export const API_ENDPOINTS = {
  activate: "/auth/activate",
  refresh: "/auth/refresh",
  revoke: "/auth/revoke",
  action: "/ai/action",
  ocr: "/ai/ocr",
} as const;

/** Access token will be refreshed this many seconds before expiry. */
export const TOKEN_REFRESH_MARGIN_SECONDS = 60;

/** Maximum text length accepted by the backend. */
export const MAX_TEXT_CHARS = 50_000;

/** Maximum image size in bytes for OCR (5 MB). */
export const MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024;
