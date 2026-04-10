import apiClient from "./client";
import { API_ENDPOINTS } from "../config";

// ---- Types matching app/schemas/ai.py ----

export type ActionType =
  | "summarize"
  | "improve"
  | "make_email"
  | "reply_email"
  | "fix_language"
  | "explain_meaning"
  | "translate_to_he"
  | "translate_to_en";

export interface AIActionRequest {
  text: string;
  action: ActionType;
}

export interface AIActionResponse {
  result: string;
}

export interface OCRRequest {
  image_base64: string;
}

export interface OCRResponse {
  result: string;
}

// ---- API calls ----

export async function runAction(
  action: ActionType,
  text: string,
): Promise<string> {
  const { data } = await apiClient.post<AIActionResponse>(
    API_ENDPOINTS.action,
    { text, action } satisfies AIActionRequest,
  );
  return data.result;
}

export async function runOCR(imageBase64: string): Promise<string> {
  const { data } = await apiClient.post<OCRResponse>(
    API_ENDPOINTS.ocr,
    { image_base64: imageBase64 } satisfies OCRRequest,
  );
  return data.result;
}
