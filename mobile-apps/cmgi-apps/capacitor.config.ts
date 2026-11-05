import type { CapacitorConfig } from '@capacitor/cli';

// CMGI Apps: the live website at / in a native shell, so every website update is in the app at once.
// Only changes to this shell (icons, permissions, plugins) need a new store version.
// Created by mobile-apps/tools/make_app.py -- change the settings there and run it again.
// CMGI_APP_URL: the public address of the site, e.g. https://cmgi-apps.de (set before building).
const base = (process.env.CMGI_APP_URL || 'https://cmgi-apps.de').replace(/\/+$/, '');

const config: CapacitorConfig = {
  // Final once the app is in the stores.
  appId: 'org.cmgi.apps',
  appName: 'CMGI Apps',
  webDir: 'www',
  // The website recognises the app by this and hides purchase buttons (store payment rules).
  appendUserAgent: 'CMGIApp',
  server: {
    url: base + '/',
    // Shown when the phone is offline or the site cannot be reached.
    errorPath: 'offline.html',
    // Jitsi video meetings (Body of Christ) open inside the app.
    allowNavigation: ['meet.jit.si'],
  },
  android: { allowMixedContent: false },
  ios: { contentInset: 'automatic' },
};

export default config;
