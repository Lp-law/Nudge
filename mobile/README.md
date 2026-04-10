# Nudge Mobile

React Native (Expo) mobile client for the Nudge AI assistant.

## Prerequisites

- Node.js 18+
- Expo CLI (`npm install -g expo-cli`)
- iOS: Xcode 15+ (macOS only)
- Android: Android Studio with an emulator or a physical device

## Setup

```bash
cd mobile
npm install
```

### Configure Backend URL

Edit `src/config.ts` and set `BACKEND_URL` to your server address:

```ts
export const BACKEND_URL = "https://your-server.example.com";
```

For local development with an emulator, use your machine's LAN IP (e.g. `http://192.168.1.100:8000`).

## Running

```bash
# Start Expo dev server
npx expo start

# Run on iOS simulator
npx expo start --ios

# Run on Android emulator
npx expo start --android
```

## Project Structure

```
mobile/
├── App.tsx                     # Root component with navigation
├── src/
│   ├── config.ts               # Backend URL, API config
│   ├── api/                    # API layer (auth, AI actions, OCR)
│   ├── store/                  # Auth context + secure token storage
│   ├── screens/                # App screens
│   ├── components/             # Reusable UI components
│   ├── hooks/                  # Custom React hooks
│   ├── i18n/                   # Hebrew (default) and English strings
│   └── utils/                  # Clipboard, layout converter, share handling
```

## Auth Flow

1. On first launch the **ActivationScreen** is shown.
2. The user enters their license key, which is exchanged for tokens via `POST /auth/activate`.
3. Tokens are stored encrypted in the device keychain (expo-secure-store).
4. The access token is automatically refreshed before expiry.
5. Logout revokes the refresh token and clears local storage.

## Share Sheet Integration

### Android

Configured in `app.json` via `intentFilters`. The app handles `ACTION_SEND` with `text/plain` MIME type automatically.

### iOS

iOS Share Extensions require a native target:

1. Run `npx expo prebuild` to generate the native project.
2. Open `ios/` in Xcode.
3. Add a Share Extension target.
4. In the extension, extract shared text and forward it to the main app via an App Group or custom URL scheme (`nudge://share?text=...`).
5. Add the App Group entitlement to both the main app and the extension.

## Building for Production

```bash
# Build for iOS
npx expo build:ios

# Build for Android
npx expo build:android

# Or use EAS Build
npx eas build --platform all
```
