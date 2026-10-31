# EventPass Studio v2 – unabhängige Event-Anmeldung und QR-Check-in

## Windows / VS Code – Start

1. Entpacke den Ordner und öffne ihn in VS Code.
2. Backend-Terminal (PowerShell):
   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   $env:EVENTPASS_ADMIN_PASSWORD="BITTE-EIN-LANGES-EIGENES-PASSWORT-WAEHLEN"
   .\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```
3. Neues Terminal (im Projekt-Hauptordner):
   ```powershell
   cd frontend
   npm.cmd install
   npm.cmd run dev
   ```
4. Öffne http://localhost:5173/ und melde dich mit dem in Schritt 2 gewählten Passwort an.
5. Erstelle ein Event. Kopiere den Anmeldelink. Öffne ihn in einem anderen Browser-Tab, registriere eine Testperson und lade das Badge herunter.
6. Wähle das Event im Admin-Dashboard aus. Scanne den QR-Code (oder verwende zum Testen „QR-Code manuell eingeben“ mit dem Inhalt `EVP:<badge_secret>`). Der Check-in wird in `backend/eventpass.sqlite3` gespeichert. Ein zweiter Scan am gleichen Tag wird als Duplikat erkannt.

## Wichtige Hinweise

- Diese Version ist ein **lokaler MVP** zum Entwickeln und Testen, kein produktionsreifer öffentlicher Registrierungsdienst.
- `localhost`-Links sind nur auf deinem eigenen PC erreichbar. Um Anmeldelinks an andere Personen zu senden, brauchst du später HTTPS-Hosting, eine öffentliche Domain und passende API-Konfiguration.
- Für Kamerazugriff auf Smartphones ist HTTPS erforderlich (außer bei localhost); Browser müssen die Kamera freigeben.
- Personenbezogene Daten und Ernährungsangaben: Vor öffentlichem Betrieb Datenschutz, Einwilligung/Informationspflichten, Berechtigungskonzept, Backups, Löschfristen und Verschlüsselung prüfen.
- Die App versendet noch keine E-Mails. Registrierte Personen müssen ihren Badge direkt herunterladen.
- Nur Teilnehmer, Gäste und Volunteers können sich selbst registrieren; Pastor/Speaker/VIP bleibt einer späteren Admin-Freigabe vorbehalten.
- Die Anmeldung ist derzeit nicht gegen automatisierte Massenanmeldungen geschützt. Für echten Betrieb Rate-Limits, E-Mail-Verifikation und sichere Passwortverwaltung ergänzen.
- `EVENTPASS_ADMIN_PASSWORD` unbedingt selbst setzen, bevor die App genutzt wird. Das Demo-Fallback-Passwort ist nicht sicher.
- Wenn Port 8000 belegt ist, läuft möglicherweise bereits dein alter Backend-Server. Stoppe diesen zuerst per Ctrl+C. Alte und neue Datenbanken werden nicht automatisch migriert.
