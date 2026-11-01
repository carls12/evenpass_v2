# CMGI Apps

Zentrale Plattform für die Webanwendungen von CMGI – eine Domain, ein Unterordner pro App.

| Pfad | Inhalt | Status |
|---|---|---|
| `/` | Portal (Startseite, Apps, About, Contact, Login) | ✅ |
| `/eventpass/` | EventPass Studio – Anmeldung, Badges, QR-Check-in | ✅ |
| `/api/eventpass/*` | EventPass-API (FastAPI) | ✅ |
| `/sermon-ai/` | Sermon Intelligence – Predigten aufnehmen, transkribieren, Berichte & Übersetzungen (EN/FR/DE) | ✅ |
| `/api/sermon-ai/*` | Sermon-API (FastAPI, OpenAI + Claude) | ✅ |

## Schnellstart (Windows)

Doppelklick auf **`Start-CMGI-Apps.bat`** → richtet beim ersten Mal alles ein, startet API, EventPass und Portal
und öffnet <http://localhost:5173>. Beenden mit **`Stop-CMGI-Apps.bat`**.

Voraussetzungen: Python 3.12+ und Node.js 20+. Lokales Admin-Passwort ohne weitere Einrichtung: `change-me-before-sharing`
(nur in der Entwicklung; in Produktion ist ein eigenes Passwort Pflicht).

Sermon Intelligence lokal: Passwort ebenfalls `change-me-before-sharing`. Für Transkription und Berichte
einmalig die Schlüssel setzen (PowerShell), danach neu starten:

```powershell
[Environment]::SetEnvironmentVariable('OPENAI_API_KEY', 'sk-...', 'User')
[Environment]::SetEnvironmentVariable('ANTHROPIC_API_KEY', 'sk-ant-...', 'User')
```

Mit Docker Desktop: `.env.example` → `.env` kopieren, Passwort eintragen, dann `Start-CMGI-Apps.bat docker`
(oder `docker compose up -d --build`) → <http://localhost>.

## Struktur

```text
apps/
  portal/               React + TypeScript + Vite (Startseite)
  eventpass/
    backend/            FastAPI, SQLite, ReportLab (PDF), Backups, Tests
    frontend/           React + Vite, base path /eventpass/
  sermon-ai/
    backend/            FastAPI, SQLite, OpenAI (Transkription), Claude (Berichte), PDF-Export, Tests
    frontend/           React + TypeScript, Aufnahme im Browser, base path /sermon-ai/
infrastructure/
  caddy/Caddyfile       Reverse Proxy + statische Auslieferung + HTTPS
  docker/               Build der Frontends
  deployment/           deploy.sh, backup.sh, restore.sh, healthcheck.sh
docs/                   Architektur, Deployment, Roadmap
compose.yaml            Produktions-Stack (3 Container)
```

## Weiterführend

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) – Aufbau, Entscheidungen, neue App hinzufügen
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) – VPS, HTTPS, Backups, Updates, Rollback, Coolify
- [docs/ROADMAP.md](docs/ROADMAP.md) – zentrales Login, PostgreSQL, offene Punkte

## Tests

```bash
cd apps/eventpass/backend && .venv/Scripts/python -m pytest -q tests   # API, Rechte, PDF, QR, Backups
cd apps/portal && npm run build                                          # Typprüfung + Build
cd apps/eventpass/frontend && npm run build
cd apps/sermon-ai/backend && .venv/Scripts/python -m pytest -q tests    # Upload, Jobs, Export, Claude/OpenAI-Anfragen (ohne Netz)
cd apps/sermon-ai/frontend && npm run build
```
