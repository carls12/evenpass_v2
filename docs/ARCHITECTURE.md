# Architektur

## Überblick

```text
Browser ──HTTPS──▶ Caddy (Container "web")
                    ├── /                 → statisches Portal         (/srv/portal)
                    ├── /eventpass/*      → statisches EventPass-UI   (/srv/eventpass)
                    ├── /register|gate|events/* → 308 auf /eventpass/… (alte Links)
                    ├── /api/eventpass/*  → eventpass-api:8000 (FastAPI, Container)
                    │                           └── Volume eventpass_data:/data (eventpass.sqlite3, badge_assets/, backups/)
                    ├── /sermon-ai/*      → statisches Sermon-UI      (/srv/sermon-ai)
                    ├── /api/sermon-ai/*  → sermon-api:8000 (FastAPI, Container) ──▶ OpenAI (Speech-to-Text), Anthropic (Claude)
                    │                           └── Volume sermon_data:/data (sermon.sqlite3, audio/, backups/)
                    └── /bodyofchrist/*   → bodyofchrist:8000 (Django, fertiges Image aus carls12/bodyofchrist-django)
                                                ├── Datenbank "bodyofchrist" in db (PostgreSQL)
                                                └── Volume bodyofchrist_media:/data/media (Avatare)

db (PostgreSQL 17, Volume db_data) – zentraler Datenbankserver, eine Datenbank + ein Login pro App,
nicht von außen erreichbar. db-setup legt beim Start fehlende Datenbanken/Logins an.
```

Ohne Body of Christ drei Container, zusammen ca. 200–350 MB RAM. Dazu kommt die zentrale PostgreSQL (~50–150 MB).
Body of Christ (eigenes Repository, nur aktiv mit `COMPOSE_PROFILES=bodyofchrist`) braucht bis zu ~400 MB –
dann 4 GB RAM einplanen.

Body of Christ ist ein vollständiges, serverseitig gerendertes Django-Projekt mit eigener Datenbank und eigenem
Login. Es wird nicht hier gebaut, sondern als versioniertes Image eingebunden (Version in `compose.yaml`), damit
der Mitentwickler nur sein Repository braucht und Änderungen erst nach bewusster Versionsänderung live gehen.

## Entscheidungen

| Entscheidung | Begründung |
|---|---|
| **Unterordner statt Subdomains** | Wunsch, ein Zertifikat, kein CORS (alles same-origin). Subdomains sind später nur ein weiterer Caddy-Block. |
| **Jede App = eigener Build** | Ein Fehler im Portal kann EventPass nicht beschädigen und umgekehrt. Neue Apps bringen ihren eigenen Stack mit. |
| **Caddy** | Automatisches HTTPS, Reverse Proxy und Static-Server in einem kleinen Binary – kein separates nginx nötig. |
| **SQLite bleibt (vorerst)** | Datenmenge klein, ein Schreibprozess, WAL-Modus. PostgreSQL kostet ~150–250 MB RAM zusätzlich ohne aktuellen Nutzen. Umstieg vorbereitet, siehe ROADMAP. |
| **API unter `/api/eventpass` und `/api`** | `/api/eventpass` ist kanonisch; `/api` bleibt als Alias, damit nichts Bestehendes bricht. |
| **QR-Inhalt `EVP:<secret>`** | Enthält keine URL → gedruckte Badges bleiben bei jeder Domain-/Pfadänderung gültig. |
| **Additive Migrationen + Backup** | Schema-Änderungen nur per `ADD COLUMN`; vor jeder Migration wird automatisch ein geprüftes Backup erstellt. Dadurch läuft auch die Vorgängerversion weiter (sicherer Rollback). |

## EventPass – Funktionen (Stand dieser Version)

Events anlegen · eigene Formularfelder · öffentliche Registrierung · manuelle Teilnehmer (Admin und Torpersonal mit Freigabe) ·
Badge-Designer mit Maßen, Texten, Hintergrund und Logo (automatisch gespeichert) · Badge-PDF · A4-Sammeldruck ·
QR-Code je Teilnehmer · Kamera-Scan (lazy geladen) · Check-in einmal pro Tag (Zeitzone `EVENTPASS_TIMEZONE`) ·
temporäre, widerrufbare Torzugänge (PBKDF2, max. 90 Tage) · Anwesenheitsübersicht.

**Noch nicht vorhanden** (bewusst nicht vorgetäuscht): Event-Stammdaten bearbeiten/löschen, automatische Live-Aktualisierung,
E-Mail-Versand, zentrale Benutzerkonten. Siehe ROADMAP.

## Sermon Intelligence – Ablauf

1. **Aufnahme im Browser**: `MediaRecorder` (Opus, 32 kbit/s ≈ 15 MB pro Stunde). Alle 10 Minuten beginnt ein neues,
   eigenständiges Segment (1,5 s Überlappung, damit an der Grenze nichts fehlt) – jedes Segment bleibt unter dem
   25-MB-Limit der Transkription. Alle 5 s wird ein Stück zuerst in **IndexedDB** gespeichert und dann hochgeladen;
   erst nach Bestätigung des Servers wird es lokal gelöscht. Funkloch, Neuladen oder Absturz verlieren daher höchstens
   wenige Sekunden. Der Bildschirm wird per Wake-Lock wach gehalten.
2. **Upload**: geordnet und idempotent (`PUT …/segments/{n}/chunks/{seq}`); doppelte Stücke werden erkannt.
3. **Transkription**: je Segment ein Aufruf an OpenAI (`whisper-1`), mit dem Ende des vorherigen Segments als Kontext.
   Fertige Teile bleiben bei einem Fehler erhalten – ein erneuter Versuch bezahlt nur den Rest.
4. **Korrektur**: Transkript ist im Browser editierbar (Namen, Bibelstellen).
5. **Berichte/Übersetzungen**: Claude (`claude-opus-5-5`, adaptive thinking, strukturierte JSON-Ausgabe für Berichte,
   serverseitiger Fallback bei Ablehnung). Das Transkript steht vorne und wird gecacht, sodass jede weitere Sprache günstiger ist.
6. **Export**: PDF (ReportLab, Montserrat) und Markdown.

Jobs laufen im API-Prozess; nach einem Neustart werden unterbrochene Jobs als „bitte erneut starten“ markiert.

## Konfiguration (Umgebungsvariablen)

| Variable | Standard | Zweck |
|---|---|---|
| `EVENTPASS_ENV` | `development` | `production`: Passwort-Pflicht, keine API-Doku |
| `EVENTPASS_ADMIN_PASSWORD` | – | Admin-Login (Produktion: ≥ 12 Zeichen) |
| `EVENTPASS_DB_PATH` | `backend/eventpass.sqlite3` | Datenbank |
| `EVENTPASS_ASSETS_DIR` | `backend/badge_assets` | hochgeladene Bilder |
| `EVENTPASS_BACKUP_DIR` | `<DB-Ordner>/backups` | automatische Backups |
| `EVENTPASS_TIMEZONE` | `Europe/Berlin` | Kalendertag für Check-ins |
| `EVENTPASS_LOGIN_LIMIT` | `10` | Fehlversuche pro IP in 15 Min. |
| `EVENTPASS_ORIGIN` | localhost-Ports | nur für Cross-Origin-Zugriffe |
| `SERMON_ADMIN_PASSWORD` | – | Login Sermon Intelligence (Produktion: ≥ 12 Zeichen) |
| `OPENAI_API_KEY` | – | Transkription |
| `ANTHROPIC_API_KEY` | – | Berichte & Übersetzungen |
| `SERMON_CLAUDE_MODEL` | `claude-opus-5-5` | z. B. `claude-sonnet-5-5` für ca. halbe Kosten |
| `SERMON_TRANSCRIBE_MODEL` | `whisper-1` | OpenAI-Transkriptionsmodell |
| `SERMON_DB_PATH` / `SERMON_AUDIO_DIR` | `backend/…` | Datenbank / Aufnahmen |

## Neue App hinzufügen

1. Code nach `apps/<name>/` (eigenes Frontend mit Vite `base: '/<name>/'`, eigenes Backend mit Prefix `/api/<name>`).
2. Eintrag in `apps/portal/src/config/apps.ts` (Status `available` + `href` erst, wenn sie wirklich läuft).
3. Caddy: `handle /api/<name>/*` und `handle_path /<name>/*` nach dem EventPass-Muster.
4. Dockerfile-Stage in `infrastructure/docker/web.Dockerfile`, Backend-Service + eigenes Volume in `compose.yaml`.
5. CI-Matrix in `.github/workflows/ci.yml` ergänzen.
