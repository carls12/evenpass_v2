# CMGI mobile apps (Android & iOS)

| Folder | App | Opens | App ID | Camera / microphone |
|---|---|---|---|---|
| `cmgi-apps/` | CMGI Apps (all tools) | `/` (portal) | `org.cmgi.apps` | both |
| `eventpass/` | EventPass | `/eventpass/` | `org.cmgi.eventpass` | camera (QR check-in) |
| `sermon-ai/` | Sermon AI | `/sermon-ai/` | `org.cmgi.sermonai` | microphone (recordings) |
| `bodyofchrist/` | Body of Christ | `/bodyofchrist/` | `org.cmgi.bodyofchrist` | both (voice messages, video meetings) |

Every app is the same small Capacitor shell around the **live website**: website updates are in all apps at
once, no new store version needed. One CMGI account works in every app; nothing can be bought inside the apps
(the site hides buy buttons, people pay on the website).

`cmgi-apps/` is the template. `tools/make_app.py` creates the other three from it (name, app ID, start page,
permissions, offline page, icon, splash screen). After changing the template or a setting in the script:

```bash
python mobile-apps/tools/make_app.py
```

## Test on an Android phone
1. GitHub → **Actions** → **Mobile apps** → **Run workflow**. In *url*, enter the address the apps should open:
   your server (`https://cmgi-apps.de`) or, before it is online, your ngrok address
   (`https://….ngrok-free.dev`, with ngrok and Start-CMGI-Apps.bat running on your computer).
2. When the run is green (about 10 minutes): open it → **Artifacts** → e.g. `eventpass-android` → download, unzip.
3. Send the `.apk` to the phone (cable, Google Drive, e-mail) and open it; allow *install unknown apps* once.
4. ngrok only: the first page is ngrok's warning → *Visit Site*.

Every push to `main` that changes `mobile-apps/` builds all apps for `https://cmgi-apps.de` automatically.

## Test on iPhone
Apple only installs signed apps. Without an Apple Developer account (99 $/year) the build is for the
**iOS Simulator on a Mac** (artifact `…-ios-simulator`: unzip, drag `App.app` onto the running simulator).
With the account: open `ios/App/App.xcodeproj` in Xcode on a Mac → *Signing & Capabilities* → your team →
run on your iPhone, or *Product → Archive* → TestFlight to share it with testers.

## Publish
1. **App IDs** are final once an app is in a store (see the table).
2. **Google Play** (one-time 25 $ for all apps): Android Studio → open `<app>/android` → *Build → Generate Signed
   App Bundle* (keep the upload key safe!) → Play Console → store listing, privacy policy URL, data-safety form →
   internal test → production.
3. **App Store** (99 $/year for all apps, needs a Mac with Xcode): *Product → Archive* → *Distribute App* →
   App Store Connect → TestFlight → review. Apple reviews web-based apps strictly: describe the native features
   (QR scanner, recordings, offline page) and give the reviewer a demo account.
