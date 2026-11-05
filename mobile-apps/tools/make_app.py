"""Creates the Android + iOS apps in mobile-apps/<app>/ from the template mobile-apps/cmgi-apps/.

Every app is the same Capacitor shell: it opens the live website at its own path, so website
updates reach the app at once. Per app: name, app ID, start page, permissions, offline page, icons.

    python mobile-apps/tools/make_app.py            # (re)creates eventpass, sermon-ai, bodyofchrist + all icons
    python mobile-apps/tools/make_app.py --icons    # only redraws the icons and splash screens

The app ID (e.g. org.cmgi.eventpass) can no longer change once an app is in a store.
"""
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]           # mobile-apps/
REPO = ROOT.parent
TEMPLATE = ROOT / 'cmgi-apps'
FONT = REPO / 'apps' / 'eventpass' / 'backend' / 'fonts' / 'Montserrat-Bold.ttf'   # SIL Open Font License
LOGO = REPO / 'apps' / 'eventpass' / 'frontend' / 'public' / 'images' / 'cmgi-logo.png'
SKIP = {'node_modules', 'build', '.gradle', 'DerivedData', 'Pods', 'xcuserdata'}

APPS = {
    'cmgi-apps':    dict(app_id='org.cmgi.apps', name='CMGI Apps', path='/', mark='logo',
                         camera='The camera scans QR codes on event badges and is used in video meetings.',
                         mic='The microphone records sermons, voice messages and video meetings.', jitsi=True),
    'eventpass':    dict(app_id='org.cmgi.eventpass', name='EventPass', path='/eventpass/', mark='EP',
                         camera='The camera scans the QR codes on event badges at the entrance.', mic=None, jitsi=False),
    'sermon-ai':    dict(app_id='org.cmgi.sermonai', name='Sermon AI', path='/sermon-ai/', mark='SI',
                         camera=None, mic='The microphone records sermons for transcription.', jitsi=False),
    'bodyofchrist': dict(app_id='org.cmgi.bodyofchrist', name='Body of Christ', path='/bodyofchrist/', mark='B',
                         camera='The camera is used in video meetings of your assembly.',
                         mic='The microphone records voice messages and is used in video meetings.', jitsi=True),
}
BLUE, BLUE_DARK, LIGHT = (23, 100, 216), (17, 63, 118), (243, 248, 255)


# ---------------------------------------------------------------- project files
def capacitor_config(key, app):
    return f"""import type {{ CapacitorConfig }} from '@capacitor/cli';

// {app['name']}: the live website at {app['path']} in a native shell, so every website update is in the app at once.
// Only changes to this shell (icons, permissions, plugins) need a new store version.
// Created by mobile-apps/tools/make_app.py -- change the settings there and run it again.
// CMGI_APP_URL: the public address of the site, e.g. https://cmgi-apps.de (set before building).
const base = (process.env.CMGI_APP_URL || 'https://cmgi-apps.de').replace(/\\/+$/, '');

const config: CapacitorConfig = {{
  // Final once the app is in the stores.
  appId: '{app['app_id']}',
  appName: '{app['name']}',
  webDir: 'www',
  // The website recognises the app by this and hides purchase buttons (store payment rules).
  appendUserAgent: 'CMGIApp',
  server: {{
    url: base + '{app['path']}',
    // Shown when the phone is offline or the site cannot be reached.
    errorPath: 'offline.html',{chr(10) + "    // Jitsi video meetings (Body of Christ) open inside the app." + chr(10) + "    allowNavigation: ['meet.jit.si']," if app['jitsi'] else ''}
  }},
  android: {{ allowMixedContent: false }},
  ios: {{ contentInset: 'automatic' }},
}};

export default config;
"""


def offline_page(app):
    name = app['name']
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>{name}</title>
  <style>
    body {{ margin: 0; min-height: 100vh; display: grid; place-items: center; background: #f3f8ff; color: #15304f;
           font-family: -apple-system, "Segoe UI", Roboto, Arial, sans-serif; text-align: center; padding: 24px; box-sizing: border-box; }}
    h1 {{ color: #1764d8; font-size: 22px; margin: 0 0 10px; }}
    p {{ color: #5f7593; line-height: 1.6; margin: 0 0 18px; }}
    button {{ background: #1764d8; color: #fff; border: 0; border-radius: 12px; padding: 12px 22px; font-size: 16px; font-weight: 700; }}
  </style>
</head>
<body>
  <div>
    <h1>{name}</h1>
    <p>No internet connection. Please check your connection and try again.<br><br>
       Keine Verbindung – bitte Internet prüfen.<br>Pas de connexion – vérifiez Internet.</p>
    <button onclick="location.reload()">Try again · Erneut versuchen</button>
  </div>
</body>
</html>
"""


def readme(key, app):
    perms = ', '.join(p for p, on in (('camera', app['camera']), ('microphone', app['mic'])) if on) or 'none'
    return f"""# {app['name']} – Android & iOS app

Opens `{app['path']}` of the CMGI Apps website (app ID `{app['app_id']}`, permissions: {perms}).
Created by `mobile-apps/tools/make_app.py`; see `mobile-apps/README.md` for building and testing.
"""


def remove_tree(path):
    """OneDrive briefly locks folders it is syncing: retry, and accept empty folders that stay behind."""
    for attempt in range(6):
        if not path.exists(): return
        try:
            shutil.rmtree(path); return
        except PermissionError:
            time.sleep(0.5 * (attempt + 1))
    leftovers = [f for f in path.rglob('*') if f.is_file()]
    if leftovers: raise PermissionError(f'could not remove {leftovers[0]}')


def copy_template(dest):
    # Overwrite in place (deleting whole folders fails while OneDrive syncs them).
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns(*SKIP), dirs_exist_ok=True)


def set_android(dest, app):
    pkg = app['app_id']
    gradle = dest / 'android/app/build.gradle'
    gradle.write_text(re.sub(r'(namespace = |applicationId )"[^"]+"', lambda m: f'{m.group(1)}"{pkg}"', gradle.read_text(encoding='utf-8')), encoding='utf-8')
    java_root = dest / 'android/app/src/main/java'
    activity = next(java_root.rglob('MainActivity.java'))
    source = re.sub(r'^package [\w.]+;', f'package {pkg};', activity.read_text(encoding='utf-8'), flags=re.M)
    target = java_root.joinpath(*pkg.split('.')) / 'MainActivity.java'
    for old in java_root.rglob('MainActivity.java'):
        os.remove(old)
    remove_tree(java_root / 'org' / 'cmgi' / 'apps')  # an empty folder that OneDrive keeps does no harm
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding='utf-8')
    strings = dest / 'android/app/src/main/res/values/strings.xml'
    s = strings.read_text(encoding='utf-8')
    for name, value in (('app_name', app['name']), ('title_activity_main', app['name']), ('package_name', pkg), ('custom_url_scheme', pkg)):
        s = re.sub(rf'(<string name="{name}">)[^<]*(</string>)', rf'\g<1>{value}\g<2>', s)
    strings.write_text(s, encoding='utf-8')
    manifest = dest / 'android/app/src/main/AndroidManifest.xml'
    m = manifest.read_text(encoding='utf-8')
    if not app['camera']:
        m = re.sub(r'.*android\.permission\.CAMERA.*\n|.*android\.hardware\.camera".*\n', '', m)
    if not app['mic']:
        m = re.sub(r'.*android\.permission\.(RECORD_AUDIO|MODIFY_AUDIO_SETTINGS).*\n|.*android\.hardware\.microphone".*\n', '', m)
    m = re.sub(r'    <!-- EventPass QR scanner.*-->\n', '    <!-- Camera / microphone for the website inside the app (see mobile-apps/tools/make_app.py). -->\n', m)
    manifest.write_text(m, encoding='utf-8')


def set_ios(dest, app):
    pbx = dest / 'ios/App/App.xcodeproj/project.pbxproj'
    pbx.write_text(re.sub(r'PRODUCT_BUNDLE_IDENTIFIER = [^;]+;', f"PRODUCT_BUNDLE_IDENTIFIER = {app['app_id']};", pbx.read_text(encoding='utf-8')), encoding='utf-8')
    plist = dest / 'ios/App/App/Info.plist'
    p = plist.read_text(encoding='utf-8')
    p = re.sub(r'(<key>CFBundleDisplayName</key>\s*<string>)[^<]*(</string>)', rf'\g<1>{app["name"]}\g<2>', p)
    for key, text in (('NSCameraUsageDescription', app['camera']), ('NSMicrophoneUsageDescription', app['mic'])):
        pattern = rf'\s*<key>{key}</key>\s*<string>[^<]*</string>'
        if text:
            p = re.sub(rf'(<key>{key}</key>\s*<string>)[^<]*(</string>)', rf'\g<1>{text}\g<2>', p)
        else:
            p = re.sub(pattern, '', p)
    plist.write_text(p, encoding='utf-8')


def set_node(dest, key, app):
    for name in ('package.json', 'package-lock.json'):
        f = dest / name
        data = json.loads(f.read_text(encoding='utf-8'))
        data['name'] = f'cmgi-mobile-{key}'
        if name == 'package.json':
            data['description'] = f"{app['name']} for Android and iOS: the website in a native shell (Capacitor)."
        else:
            data['packages'][''].update(name=f'cmgi-mobile-{key}')
        f.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def write_project(key, app):
    dest = ROOT / key
    if key != 'cmgi-apps':
        copy_template(dest)
        set_android(dest, app)
        set_ios(dest, app)
        set_node(dest, key, app)
        (dest / 'README.md').write_text(readme(key, app), encoding='utf-8')
    (dest / 'capacitor.config.ts').write_text(capacitor_config(key, app), encoding='utf-8')
    for page in ('offline.html', 'index.html'):
        (dest / 'www' / page).write_text(offline_page(app), encoding='utf-8')


# ---------------------------------------------------------------- icons and splash screens
def gradient(size):
    w, h = size
    img = Image.new('RGB', size, BLUE)
    px = img.load()
    for y in range(h):
        for x in range(w):
            t = (x / max(w - 1, 1) + y / max(h - 1, 1)) / 2
            px[x, y] = tuple(int(BLUE[i] + (BLUE_DARK[i] - BLUE[i]) * t * 0.55) for i in range(3))
    return img


def mark_image(app, size, on_blue=True):
    """The app's mark on a transparent square: CMGI logo, or white letters."""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    if app['mark'] == 'logo':
        logo = Image.open(LOGO).convert('RGBA').resize((size, size), Image.LANCZOS)
        img.alpha_composite(logo)
        return img
    text = app['mark']
    draw = ImageDraw.Draw(img)
    font_size = int(size * (0.62 if len(text) == 1 else 0.46))
    font = ImageFont.truetype(str(FONT), font_size)
    box = draw.textbbox((0, 0), text, font=font)
    x = (size - (box[2] - box[0])) / 2 - box[0]
    y = (size - (box[3] - box[1])) / 2 - box[1]
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255) if on_blue else BLUE + (255,))
    return img


def tile(app, size):
    """Full square icon (iOS rounds it; Android legacy icon)."""
    if app['mark'] == 'logo':
        base = Image.new('RGBA', (size, size), (255, 255, 255, 255))
        base.alpha_composite(mark_image(app, int(size * 0.86)), (int(size * 0.07), int(size * 0.07)))
        return base
    base = gradient((size, size)).convert('RGBA')
    base.alpha_composite(mark_image(app, size))
    return base


def rounded(img, radius_ratio):
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, img.size[0] - 1, img.size[1] - 1), radius=int(img.size[0] * radius_ratio), fill=255)
    out = Image.new('RGBA', img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def splash(app, size):
    w, h = size
    img = Image.new('RGB', size, LIGHT)
    s = int(min(w, h) * 0.26)
    icon = rounded(tile(app, s * 2).resize((s, s), Image.LANCZOS), 0.22)
    img.paste(icon, ((w - s) // 2, int(h / 2 - s * 0.75)), icon)
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(str(FONT), max(14, int(min(w, h) * 0.055)))
    box = draw.textbbox((0, 0), app['name'], font=font)
    draw.text(((w - (box[2] - box[0])) / 2 - box[0], int(h / 2 + s * 0.40)), app['name'], font=font, fill=BLUE_DARK)
    return img


def draw_icons(key, app):
    dest = ROOT / key
    res = dest / 'android/app/src/main/res'
    for f in res.glob('mipmap-*/*.png'):
        size = Image.open(f).size[0]
        if f.name == 'ic_launcher_foreground.png':
            # Adaptive icon: the mark inside the 66 % safe zone; the background colour comes from the XML below.
            fg = Image.new('RGBA', (size, size), (0, 0, 0, 0))
            inner = int(size * 0.5)
            fg.alpha_composite(mark_image(app, inner), ((size - inner) // 2, (size - inner) // 2))
            fg.save(f)
        elif f.name == 'ic_launcher_round.png':
            big = tile(app, size * 4)
            mask = Image.new('L', big.size, 0)
            ImageDraw.Draw(mask).ellipse((0, 0, big.size[0] - 1, big.size[1] - 1), fill=255)
            out = Image.new('RGBA', big.size, (0, 0, 0, 0)); out.paste(big, (0, 0), mask)
            out.resize((size, size), Image.LANCZOS).save(f)
        else:
            rounded(tile(app, size * 4), 0.2).resize((size, size), Image.LANCZOS).save(f)
    color = '#FFFFFF' if app['mark'] == 'logo' else '#1764D8'
    (res / 'values/ic_launcher_background.xml').write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">{color}</color>\n</resources>\n', encoding='utf-8')
    for f in res.glob('drawable*/splash.png'):
        splash(app, Image.open(f).size).save(f)
    assets = dest / 'ios/App/App/Assets.xcassets'
    tile(app, 1024).convert('RGB').save(assets / 'AppIcon.appiconset/AppIcon-512@2x.png')  # iOS icons: no transparency
    for f in (assets / 'Splash.imageset').glob('*.png'):
        splash(app, Image.open(f).size).save(f)


if __name__ == '__main__':
    only_icons = '--icons' in sys.argv
    for key, app in APPS.items():
        if not only_icons:
            write_project(key, app)
        draw_icons(key, app)
        print(f'{key:13} {app["app_id"]:24} {app["path"]}')
