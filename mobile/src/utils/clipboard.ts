import * as Clipboard from "expo-clipboard";

/**
 * EN-to-HE keyboard layout mapping.
 * Identical to client/app/layout_converter.py EN_TO_HE_MAP.
 */
const EN_TO_HE_MAP: Record<string, string> = {
  q: "/",
  w: "'",
  e: "\u05E7", // ק
  r: "\u05E8", // ר
  t: "\u05D0", // א
  y: "\u05D8", // ט
  u: "\u05D5", // ו
  i: "\u05DF", // ן
  o: "\u05DD", // ם
  p: "\u05E4", // פ
  "[": "]",
  "]": "[",
  "\\": "\\",
  a: "\u05E9", // ש
  s: "\u05D3", // ד
  d: "\u05D2", // ג
  f: "\u05DB", // כ
  g: "\u05E2", // ע
  h: "\u05D9", // י
  j: "\u05D7", // ח
  k: "\u05DC", // ל
  l: "\u05DA", // ך
  ";": "\u05E3", // ף
  "'": ",",
  z: "\u05D6", // ז
  x: "\u05E1", // ס
  c: "\u05D1", // ב
  v: "\u05D4", // ה
  b: "\u05E0", // נ
  n: "\u05DE", // מ
  m: "\u05E6", // צ
  ",": "\u05EA", // ת
  ".": "\u05E5", // ץ
  "/": ".",
};

/**
 * Convert text typed on an EN keyboard layout to Hebrew characters.
 * This is a local-only operation (no server call needed).
 */
export function convertEnLayoutToHebrew(text: string): string {
  const output: string[] = [];
  for (const char of text) {
    const mapped = EN_TO_HE_MAP[char.toLowerCase()];
    output.push(mapped !== undefined ? mapped : char);
  }
  return output.join("");
}

/** Read text from the system clipboard. */
export async function readClipboard(): Promise<string> {
  return Clipboard.getStringAsync();
}

/** Write text to the system clipboard. */
export async function writeClipboard(text: string): Promise<void> {
  await Clipboard.setStringAsync(text);
}
