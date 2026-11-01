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
