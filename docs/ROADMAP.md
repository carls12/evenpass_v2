# Roadmap

## Erledigt in diesem Schritt

- Portal (`/`) mit Apps, About, Contact, Login – responsive, App-Registry in `apps/portal/src/config/apps.ts`
- EventPass unter `/eventpass/`, API unter `/api/eventpass/*` (Alias `/api` bleibt), alte Links werden umgeleitet
- Allgemeiner Tor-Login `/eventpass/gate` (leitet nach Anmeldung zum richtigen Event)
- Login-Rate-Limit, Passwortpflicht in Produktion, API-Doku in Produktion aus
- Check-in-Tag nach Event-Zeitzone statt Serveruhr
- Backup vor Migrationen, `backup.py` (Backup/Restore/Import), Server-Skripte, Deploy mit Rollback
- Docker (2 Container), Caddy, CI mit Docker-Smoke-Test, 19 Backend-Tests
- Datenbank, `node_modules`, Caches aus Git entfernt (`.gitignore`)

## Sermon Intelligence (umgesetzt)

Aufnahme im Browser mit lokaler Zwischenspeicherung, Transkription (OpenAI), editierbares Transkript, strukturierte
Berichte und Volltext-Übersetzungen EN/FR/DE (Claude), Export PDF/Markdown, eigene Datenbank und eigenes Login.

Mögliche Erweiterungen: Datei-Upload vorhandener Aufnahmen, Teilen eines Berichts per Link, Sprecherkennzeichnung,
Kostenübersicht pro Predigt, Ausgabe als Word-Dokument.

## Body of Christ (eingebunden, noch nicht aktiv)

Eigenes Repository `carls12/bodyofchrist-django` (Django, zentrale PostgreSQL). Plattform-Seite fertig: Route `/bodyofchrist/`,
Container (abschaltbar per Profil) + eigene Datenbank in der zentralen PostgreSQL, Backups, Portal-Karte („Coming Soon“). Offen: Pull Request #2 im
App-Repo mergen, Release `v0.1.0`, Server-Login für das private Image, Variablen setzen (docs/DEPLOYMENT.md).
Später: Videoanruf-Signalisierung (bisher Node-Server außerhalb des Repos) – `/meet` nutzt Jitsi und läuft schon.

## Als Nächstes (Vorschlag)

1. **Event bearbeiten/löschen** (fehlt bisher) – inkl. Schutz vor Löschen bei vorhandenen Check-ins.
2. **Live-Übersicht**: automatische Aktualisierung (Polling alle 10 s; ressourcenschonender als WebSockets).
3. **Impressum & Datenschutz** im Portal.

## Zentrales CMGI-Login (Phase „Accounts“)

Ziel-Rollen: Platform Super Admin · App Admin · Event Admin · Gate Staff · Participant.

Geplanter, schrittweiser Weg – ohne bestehende Zugänge ungültig zu machen:

1. Neues Modul `apps/accounts` (FastAPI) mit Tabellen `users`, `app_roles(user, app, role, scope)`.
   Passwörter mit Argon2id, Sessions als **HttpOnly-Cookie** auf der gemeinsamen Domain (same-origin ⇒ kein Token im JS).
2. EventPass akzeptiert **zusätzlich** die zentrale Session (Rolle `eventpass:admin` bzw. `event_admin` für bestimmte Events).
   Das bisherige Admin-Passwort und die Torzugänge funktionieren parallel weiter.
3. Bestehende Torzugänge werden 1:1 als `gate_staff`-Rollen übernommen (Hashes bleiben, kein Passwort-Reset nötig).
4. Erst wenn alle Admins zentrale Konten nutzen: Admin-Passwort-Login per Schalter deaktivieren.
5. Passwortänderung, Passwort-Reset per E-Mail (benötigt SMTP – z. B. vorhandenes Postfach), optional 2FA (TOTP).

## Konto, Pro & Mobile-App (Entscheidung 2026-11-03)

Ein CMGI-Konto für alle Apps; **ein Pro-Abo für alle Apps** (Stripe), KI-Minuten für Sermon separat;
14 Tage Pro + 5 KI-Minuten für jedes neue Konto; **eine** Mobile-App aus der Website (Capacitor), Bezahlung
auf der Website.

1. ✅ Konto-Dienst (`apps/accounts`), Portal-Seiten Login/Konto/Admin/Preise, Admin vergibt Pro & Minuten.
2. Apps anbinden: EventPass (eigene Events pro Konto; Badges + Einlass = Pro), Sermon (Aufnahmen pro Konto,
   Transkription bucht KI-Minuten), Body of Christ (Login über das CMGI-Konto, Sperren nach Ablauf des Tests).
3. Bezahlung mit Stripe: Pro-Abo, Minuten-Pakete, Kundenportal (Kündigen), Webhook schaltet frei.
4. Mobile-App (Capacitor) für Play Store und App Store, nativer QR-Scanner.

## Zentrale Datenbank (PostgreSQL) – schrittweise

Entscheidung (2026-11-03): ein zentraler PostgreSQL-Server, eine Datenbank + ein Login pro App.

1. ✅ Server `db` + `db-setup` (idempotent), Backups je Datenbank, Body of Christ nutzt PostgreSQL.
2. EventPass: Datenzugriff auf PostgreSQL umstellen (Tests gegen PostgreSQL), Migration mit Wartungsmodus →
   `backup.py` → Kopierskript SQLite → PostgreSQL → **Validierung** (Zeilenzahlen je Tabelle, alle QR-Secrets
   vorhanden) → Umschalten; SQLite-Datei bleibt als Fallback liegen.
3. Sermon Intelligence: gleiches Vorgehen (Audiodateien bleiben im Volume, nur die Daten wandern).
