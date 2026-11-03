import type { CapacitorConfig } from '@capacitor/cli';

// The app shows the live CMGI Apps website, so every website update is in the app at once.
// Only changes to this native shell (icons, permissions, plugins) need a new store version.
// CMGI_APP_URL: the public address of the site, e.g. https://cmgi-apps.de (set before building).
const url = process.env.CMGI_APP_URL || 'https://cmgi-apps.de';

const config: CapacitorConfig = {
  // Final once the app is in the stores — change it before the first upload if needed.
  appId: 'org.cmgi.apps',
  appName: 'CMGI Apps',
  webDir: 'www',
  // The website recognises the app by this and hides purchase buttons (store payment rules).
  appendUserAgent: 'CMGIApp',
  server: {
    url,
    // Shown when the phone is offline or the site cannot be reached.
    errorPath: 'offline.html',
    // Jitsi video meetings (Body of Christ) open inside the app.
    allowNavigation: ['meet.jit.si'],
  },
  android: { allowMixedContent: false },
  ios: { contentInset: 'automatic' },
};

export default config;
