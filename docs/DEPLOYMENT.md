# Deployment auf einem VPS

## Server-Empfehlung (5–10 €/Monat)

| Anbieter | Tarif (Richtwert) | RAM | Hinweis |
|---|---|---|---|
| Hetzner Cloud | CX22 / CAX11 | 4 GB | Standort DE/FI, einfache Snapshots |
| netcup | VPS 1000 | 8 GB | sehr viel RAM fürs Geld |

Preise ändern sich – vor dem Kauf prüfen. Ubuntu 24.04 LTS wählen. Für **nur Docker Compose** reichen 2 GB;
mit **Coolify** (~1 GB Eigenbedarf) mindestens 4 GB.

## Ersteinrichtung (Docker Compose, ohne Coolify)

```bash
# als root auf dem neuen Server
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh
adduser --disabled-password deploy && usermod -aG docker deploy
ufw allow OpenSSH && ufw allow 80 && ufw allow 443 && ufw enable

# als deploy
git clone https://github.com/carls12/evenpass_v2.git /opt/cmgi-apps   # Verzeichnis vorher anlegen und deploy gehören lassen
cd /opt/cmgi-apps
cp .env.example .env && nano .env        # CMGI_SITE_ADDRESS, EVENTPASS_ADMIN_PASSWORD, SERMON_ADMIN_PASSWORD, OPENAI_API_KEY, ANTHROPIC_API_KEY
infrastructure/deployment/deploy.sh
```

DNS: A-Record (und AAAA) für `cmgi-apps.de` auf die Server-IP. Caddy holt das HTTPS-Zertifikat automatisch,
sobald die Domain auf den Server zeigt. Solange es keine Domain gibt: `CMGI_SITE_ADDRESS=:80` (nur HTTP –
die Handy-Kamera funktioniert dann **nicht**, Browser erlauben sie nur über HTTPS).

Container starten nach einem Server-Neustart von selbst (`restart: unless-stopped`) und werden bei Absturz neu
gestartet; Docker prüft sie alle 30 s per Health-Check.

## Bestehende Daten übernehmen

Lokale Datenbank (z. B. `apps/eventpass/backend/eventpass.sqlite3`) auf den Server kopieren und importieren:

```bash
scp eventpass.sqlite3 deploy@SERVER:/tmp/
infrastructure/deployment/restore.sh /tmp/eventpass.sqlite3   # prüft Integrität, sichert den aktuellen Stand vorher
```

Hochgeladene Badge-Bilder liegen lokal in `badge_assets/`. Der einfachste Weg: im Admin-Bereich erneut hochladen.

## Updates & Rollback

```bash
infrastructure/deployment/deploy.sh           # Backup → Build → Start → Health-Check → bei Fehler automatisch zurück
infrastructure/deployment/deploy.sh <commit>  # bestimmte Version / manueller Rollback
```

Über GitHub: Workflow **Deploy** manuell starten (Actions → Deploy → Run workflow). Einmalig einrichten:
Settings → Environments → `production` mit dir als *Required reviewer*; Secrets `DEPLOY_HOST`, `DEPLOY_USER`,
`DEPLOY_SSH_KEY` (eigener Deploy-Key), `DEPLOY_KNOWN_HOSTS` (`ssh-keyscan SERVER`).

Ablauf: lokal entwickeln → testen → `git push` → CI (Tests, Builds, Docker-Smoke-Test) → Deploy freigeben.

## API-Schlüssel für Sermon Intelligence

- **OpenAI** (Transkription): <https://platform.openai.com/api-keys> – Guthaben aufladen, ca. 0,36 $ pro Stunde Audio.
- **Anthropic** (Berichte, Übersetzungen): <https://console.anthropic.com/> – ca. 0,30 $ je Sprache und Predigtstunde
  für einen Bericht, ebenso viel für eine Volltext-Übersetzung (Richtwerte).
- In beiden Konsolen ein **monatliches Ausgabenlimit** setzen. Schlüssel nur in `.env` auf dem Server, nie ins Repository.
- Ohne Schlüssel funktioniert Aufnehmen und Abspielen; die App zeigt einen Hinweis statt der KI-Funktionen.

## Body of Christ (drittes Tool, eigenes Repository)

Body of Christ wird im privaten Repository `carls12/bodyofchrist-django` entwickelt (dort arbeitet auch
der Mitentwickler – er braucht keinen Zugang zu diesem Repository). GitHub baut daraus bei jedem Release
ein fertiges Docker-Image `ghcr.io/carls12/bodyofchrist-django:<version>`. Hier wird nur festgelegt,
**welche Version** läuft – ein Push im anderen Repository ändert die Live-Seite nie von selbst.

**Einmalig einrichten**

1. Im Body-of-Christ-Repo den Pull Request „Deploy on the CMGI Apps platform“ mergen und ein Release
   `v0.1.0` anlegen (GitHub → Releases). Danach existiert das Image.
2. Server darf das private Image laden: auf GitHub ein *Personal access token (classic)* nur mit
   `read:packages` erstellen, dann auf dem Server einmal
   `echo <TOKEN> | docker login ghcr.io -u carls12 --password-stdin`.
3. In `.env`: `COMPOSE_PROFILES=bodyofchrist`, `BODYOFCHRIST_SECRET_KEY`, `BODYOFCHRIST_TOTP_ENCRYPTION_KEY`,
   `BODYOFCHRIST_DB_PASSWORD`, `BODYOFCHRIST_SUPER_ADMIN_EMAIL`, `BODYOFCHRIST_ALLOWED_HOSTS=cmgi-apps.de,localhost`,
   bei HTTPS zusätzlich `BODYOFCHRIST_SECURE_COOKIES=True` und `BODYOFCHRIST_CSRF_TRUSTED_ORIGINS=https://cmgi-apps.de`.
   Den TOTP-Schlüssel im Passwort-Manager sichern – geht er verloren, sind alle 2FA-Einrichtungen ungültig.
4. Deployen (`infrastructure/deployment/deploy.sh`). Dann in `apps/portal/src/config/apps.ts` die Karte auf
   `status: 'available'` und `href: '/bodyofchrist/'` stellen und erneut deployen.
5. Google-Login (optional): in der Google Cloud Console `https://cmgi-apps.de/bodyofchrist/google/callback`
   als Redirect-URI eintragen. Die Mobile-App nutzt als API-Adresse `https://cmgi-apps.de/bodyofchrist/api/v1`.

**Neue Version übernehmen:** Mitentwickler erstellt Release `v0.2.0` → in `compose.yaml` die Version
(`bodyofchrist-django:v0.2.0`) ändern, committen, deployen. Zurück: alte Versionsnummer, erneut deployen.
Datenbank-Migrationen laufen beim Start automatisch; `deploy.sh` macht vorher ein Backup.

**Daten:** Datenbank `bodyofchrist` in der zentralen PostgreSQL (siehe unten), Avatare im Volume
`bodyofchrist_media` (Backup: `bodyofchrist-media-<Zeit>.tar.gz`).

Arbeitsspeicher: Body of Christ braucht bis zu ~400 MB – mit allen Tools 4 GB RAM einplanen.

## Zentrales CMGI-Konto (Login für alle Apps)

Ein Konto für alle Tools: Anmeldung unter `/login`, Konto unter `/account`, Admin-Konsole unter `/admin`.
Die Sitzung ist ein Cookie für die ganze Domain – wer im Portal angemeldet ist, ist in allen Apps angemeldet
(Mobile-App: derselbe Token als `Authorization: Bearer`).

- Pflicht in `.env`: `ACCOUNTS_DB_PASSWORD`, `ACCOUNTS_INTERNAL_KEY` (≥ 24 Zeichen, nur URL-sichere Zeichen,
  z. B. `python -c "import secrets; print(secrets.token_urlsafe(32))"`), `CMGI_ADMIN_EMAILS` (deine E-Mail – nur
  diese Adressen sehen `/admin`; Admin-Rechte stehen bewusst nicht in der Datenbank).
- Mit HTTPS: `CMGI_SECURE_COOKIES=true`, `CMGI_PUBLIC_URL=https://cmgi-apps.de`.
- E-Mail (Bestätigung, Passwort vergessen) nutzt die EventPass-SMTP-Einstellungen. Ohne SMTP werden Konten sofort
  bestätigt, und Reset-Links erstellst du in der Admin-Konsole.
- Jedes neue Konto bekommt nach der E-Mail-Bestätigung **14 Tage Pro** und **5 Minuten** KI-Transkription.
- In der Admin-Konsole: Pro vergeben (1/3/12 Monate oder ohne Ende), KI-Minuten buchen, Konten deaktivieren,
  Passwort-Reset-Link erzeugen. Jede Aktion wird protokolliert.

## Zentrale Datenbank (PostgreSQL)

Ein Datenbankserver (`db`) für die ganze Plattform. Jede App hat **eine eigene Datenbank mit eigenem Login**
und kann nur ihre eigene Datenbank öffnen. Der Server ist von außen nicht erreichbar.

| App | Datenbank / Login | Passwort in `.env` | Stand |
|---|---|---|---|
| CMGI-Konten | `accounts` | `ACCOUNTS_DB_PASSWORD` | nutzt PostgreSQL |
| Body of Christ | `bodyofchrist` | `BODYOFCHRIST_DB_PASSWORD` | nutzt PostgreSQL |
| EventPass | – | – | noch SQLite (Umstellung: Schritt 2) |
| Sermon Intelligence | – | – | noch SQLite (Umstellung: Schritt 3) |

- `POSTGRES_PASSWORD` (Pflicht) ist das Admin-Passwort; Apps benutzen es nie.
- Beim Start legt der Dienst `db-setup` fehlende Datenbanken/Logins an und übernimmt geänderte Passwörter
  aus `.env` – er löscht nie etwas. Neue App: eine Zeile in `infrastructure/database/setup.sh` + Passwort in `.env`.
- **Backup:** `backup.sh` sichert jede App-Datenbank einzeln (`postgres-<app>-<Zeit>.dump`, wird nach dem
  Schreiben geprüft) und die Logins (`postgres-globals-<Zeit>.sql`).
- **Wiederherstellen** einer App (überschreibt nur diese Datenbank; App vorher stoppen):

  ```bash
  docker compose stop bodyofchrist
  docker compose exec -T db pg_restore -U postgres --clean --if-exists -d bodyofchrist < postgres-bodyofchrist-<Zeit>.dump
  docker compose start bodyofchrist
  ```

## Badge per E-Mail (EventPass)

Nach der Anmeldung bekommt jede Person ihren Badge (PDF im Anhang + QR-Code + Download-Link) per E-Mail.
Ohne Einstellungen wird nichts verschickt; die Anmeldung funktioniert dann wie bisher.

1. SMTP-Zugang besorgen – z. B. **Brevo** (kostenlos bis 300 Mails/Tag) oder ein Google-Konto mit **App-Passwort**.
   Beim Anbieter die Absenderadresse bzw. Domain bestätigen, sonst landen Mails im Spam.
2. In `.env` setzen: `EVENTPASS_SMTP_HOST`, `EVENTPASS_SMTP_USER`, `EVENTPASS_SMTP_PASSWORD`, `EVENTPASS_MAIL_FROM`
   und `EVENTPASS_PUBLIC_URL` (z. B. `https://cmgi-apps.de`, für den Link in der Mail). Dann `docker compose up -d`.
3. Kontrolle: In der Teilnehmerliste zeigt die Spalte „Badge-Mail“ *gesendet* oder *fehlgeschlagen*
   (Fehler beim Darüberfahren). Mit „Erneut senden“ lässt sich jede Mail wiederholen.

Lokal (Start-CMGI-Apps.bat) liest die API keine `.env`; zum Testen die Variablen vorher im Terminal setzen.

## Backups

- **Automatisch** vor jeder Schema-Migration (im Volume unter `/data/backups`) und vor jedem Deployment.
- **Täglich** per Cron:
  ```cron
  15 3 * * * /opt/cmgi-apps/infrastructure/deployment/backup.sh >> /var/log/cmgi-backup.log 2>&1
  ```
  Legt `eventpass-<zeit>.tar.gz` unter `BACKUP_DEST` ab (Standard `/var/backups/cmgi-apps`, 30 Tage).
- **Extern (dringend empfohlen)**: Kopie außerhalb des Servers, z. B. Hetzner Storage Box mit `rclone`
  (Zeile am Ende von `backup.sh`) – ein Backup auf demselben Server schützt nicht vor dessen Verlust.
- **Wiederherstellen**: `infrastructure/deployment/restore.sh /var/backups/cmgi-apps/eventpass-….tar.gz`
- **Probe**: Einmal im Quartal ein Backup auf einer lokalen Docker-Installation wiederherstellen.

Lokal (Windows): `cd apps\eventpass\backend` → `.venv\Scripts\python backup.py` (Liste: `--list`).

## Monitoring & Logs

- Logs: `docker compose logs -f eventpass-api web` (rotiert, max. 3 × 10 MB pro Container).
- Status: `docker compose ps` zeigt `healthy`/`unhealthy`.
- Erreichbarkeit von außen: kostenloser Monitor (z. B. UptimeRobot oder ein selbst gehostetes Uptime Kuma)
  auf `https://cmgi-apps.de/api/eventpass/health` – meldet per E-Mail, wenn die Seite ausfällt.

## Coolify (optional)

1. Coolify auf dem VPS installieren (bringt einen eigenen Proxy auf 80/443 mit).
2. Neue Ressource → *Docker Compose* → dieses Repository, Datei `compose.yaml`.
3. Umgebungsvariablen in Coolify setzen: `CMGI_SITE_ADDRESS=:80`, `EVENTPASS_ADMIN_PASSWORD=…`,
   `HTTP_PORT`/`HTTPS_PORT` auf freie Ports (z. B. 8080/8443) oder Port-Mapping entfernen.
4. Domain `cmgi-apps.de` dem Service `web` (Port 80) zuweisen – HTTPS übernimmt Coolify.
5. Volumes bleiben bei Redeploys erhalten; Backups wie oben oder über Coolifys Volume-Backups.

## Sicherheits-Checkliste vor dem Livegang

- [ ] Starkes `EVENTPASS_ADMIN_PASSWORD` in `.env` (nie committen)
- [ ] HTTPS aktiv (Domain gesetzt), Firewall nur 22/80/443
- [ ] SSH nur mit Schlüssel (`PasswordAuthentication no`)
- [ ] `unattended-upgrades` für Sicherheitsupdates
- [ ] Tägliches + externes Backup eingerichtet und einmal getestet
- [ ] **Impressum und Datenschutzerklärung** im Portal ergänzen (in Deutschland Pflicht; EventPass verarbeitet personenbezogene Daten)
