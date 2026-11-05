# CMGI Apps – mobile app (Android & iOS)

This is also the template for the other apps in `mobile-apps/` (see `../README.md` and `../tools/make_app.py`).

One app for all CMGI tools. It opens the live website (`capacitor.config.ts → server.url`) in a native shell,
so **every website update is in the app immediately** — no new store version needed. A new app version is only
needed when this folder changes (icon, name, permissions, native plugins).

- Signed in on the website = signed in in the app (same CMGI account).
- Camera (EventPass QR scanner) and microphone (Sermon recordings) are declared for Android and iOS.
- Offline: `www/offline.html` is shown, with a "Try again" button.
- **No purchases inside the app** (Apple/Google would require their own billing with 15–30 % fees): the site
  recognises the app (`CMGIApp` in the user agent) and hides buy buttons. People pay on the website; Pro and AI
  minutes are then unlocked in the app too.

## Test on an Android phone

GitHub → Actions → **Mobile apps** → latest run → *Artifacts* → `cmgi-apps-android` → install the APK
(allow "unknown sources"). To point it at another address: *Run workflow* with the `url` field.

## Publish

1. **Final app ID**: `appId` in `capacitor.config.ts` (now `org.cmgi.apps`) cannot change after the first upload.
2. **Icon & splash**: drawn by `../tools/make_app.py` (CMGI logo).
3. **Google Play** (one-time 25 $): Android Studio → `npm run android` → *Build → Generate Signed App Bundle*
   (keep the upload key safe!) → upload the `.aab` in the Play Console → store listing, privacy policy URL,
   data-safety form → internal test → production.
4. **App Store** (99 $/year, needs a Mac with Xcode): `npm run ios` → set the team under *Signing & Capabilities*
   → *Product → Archive* → *Distribute App* → App Store Connect → TestFlight → review.
   Apple reviews web-based apps strictly: describe the native features (QR scanner, recordings, offline page)
   and provide a demo account for the reviewer.

After changing anything in this folder: `npx cap sync`, then build and upload a new version.
