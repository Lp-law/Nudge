import type { TranslationKeys } from "./he";

const en: Record<TranslationKeys, string> = {
  // General
  appTitle: "Nudge",
  loading: "Loading...",
  error: "Error",
  cancel: "Cancel",
  copy: "Copy",
  copied: "Copied",
  back: "Back",
  settings: "Settings",
  about: "About",
  logout: "Log out",
  logoutConfirm: "Log out of Nudge?",
  logoutConfirmYes: "Log out",

  // Activation
  activationTitle: "Activate Nudge",
  activationSubtitle:
    "Enter the license key you received with your purchase. The connection is secure.",
  activationLicenseLabel: "License key",
  activationSubmit: "Activate",
  activationErrorEmpty: "License key is too short. Please paste the full key.",
  activationFailedGeneric:
    "Activation failed. Check the key or your internet connection.",

  // Home
  homeTitle: "Nudge",
  homeInputPlaceholder: "Paste or type text here...",
  homeSelectAction: "Select action",

  // Actions
  action_summarize: "Summarize",
  action_improve: "Improve",
  action_make_email: "Make email",
  action_reply_email: "Draft reply",
  action_fix_language: "Fix language",
  action_translate_to_he: "Translate to Hebrew",
  action_translate_to_en: "Translate to English",
  action_fix_layout_he: "EN > HE layout",
  action_explain_meaning: "Explain meaning",

  // Result
  resultTitle: "Result",
  resultCopied: "Result copied to clipboard.",
  resultEmpty: "Empty result",

  // OCR
  ocrTitle: "Extract text (OCR)",
  ocrPickCamera: "Take photo",
  ocrPickGallery: "Choose from gallery",
  ocrProcessing: "Processing...",
  ocrNoImage: "No image selected.",
  ocrExtractButton: "Extract text",

  // Errors
  errorInvalidText: "No valid text detected",
  errorNoImage: "No image found",
  errorCancelled: "Action cancelled",
  errorTimeout: "Timed out",
  errorNetwork: "Network error",
  errorRequestFailed: "Request failed",
  errorBadResponse: "Bad response",
  errorEmptyResult: "Empty result",
  errorOcrFailed: "OCR failed",
  errorRateLimited: "Too many requests. Please try again shortly.",
  errorUnauthorized:
    "Session expired or rejected. Please try again or re-activate.",
  errorInvalidLicense: "Invalid license key.",
  errorDeviceMismatch:
    "This license is already active on another device. Contact support.",
  errorActivationUnavailable: "Activation is not available. Contact support.",
  errorTooManyActivations:
    "Too many activation attempts. Try again in a few minutes.",
  errorServerError: "Temporary server error.",

  // Settings
  settingsTitle: "Settings",
  settingsLanguage: "Language",
  settingsVersion: "Version",
  settingsBuildInfo: "Build info",
} as const;

export default en;
