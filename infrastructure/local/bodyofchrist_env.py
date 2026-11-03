"""Writes a local .env for Body of Christ (used by Start-CMGI-Apps.bat, development only).

SQLite instead of MySQL, the /bodyofchrist sub-path behind the local portal, and sign-in with
the local CMGI account service on port 8020. Fresh secrets are generated once.
"""
import secrets
import sys
from pathlib import Path

from cryptography.fernet import Fernet

target = Path(sys.argv[1])
if target.exists():
    sys.exit(0)  # never overwrite: the TOTP key must stay the same
target.write_text(f"""# Local development for the CMGI Apps platform (created by Start-CMGI-Apps.bat).
DJANGO_DEBUG=True
SECRET_KEY={secrets.token_urlsafe(48)}
TOTP_ENCRYPTION_KEY={Fernet.generate_key().decode()}
DB_ENGINE=sqlite
URL_PREFIX=bodyofchrist
ALLOWED_HOSTS=localhost,127.0.0.1
CMGI_ACCOUNTS_URL=http://127.0.0.1:8020/api/accounts
CMGI_PORTAL_URL=/
CMGI_INTERNAL_KEY=local-dev-internal-key-0123456789
SERVE_MEDIA=True
APP_TIMEZONE=Europe/Berlin
""", encoding='utf-8')
print(f'created {target}')
