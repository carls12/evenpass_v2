#!/usr/bin/env bash
# One-time: creates .env on a new server with strong random passwords for every database
# and internal key, the domain and the platform admin. Never overwrites an existing .env.
#   infrastructure/deployment/first-setup.sh cmgi-apps.de you@example.org
#   infrastructure/deployment/first-setup.sh :80 you@example.org      # no domain yet (HTTP only)
set -euo pipefail
cd "$(dirname "$0")/../.."

DOMAIN="${1:?Usage: first-setup.sh <domain or :80> <admin email>}"
ADMIN="${2:?Usage: first-setup.sh <domain or :80> <admin email>}"
[ -f .env ] && { echo ".env already exists — nothing changed. Edit it with: nano .env"; exit 1; }

python3 - "$DOMAIN" "$ADMIN" <<'PY'
import base64, os, re, secrets, sys

domain, admin = sys.argv[1], sys.argv[2].strip().lower()
https = domain != ':80' and not domain.startswith(':')
url = f'https://{domain}' if https else ''
key = lambda: secrets.token_urlsafe(32)
values = {
    'CMGI_SITE_ADDRESS': domain,
    'EVENTPASS_ADMIN_PASSWORD': key(), 'SERMON_ADMIN_PASSWORD': key(),
    'POSTGRES_PASSWORD': key(), 'EVENTPASS_DB_PASSWORD': key(), 'SERMON_DB_PASSWORD': key(),
    'ACCOUNTS_DB_PASSWORD': key(), 'ACCOUNTS_INTERNAL_KEY': key(),
    'CMGI_ADMIN_EMAILS': admin,
    'CMGI_PUBLIC_URL': url, 'EVENTPASS_PUBLIC_URL': url,
    'CMGI_SECURE_COOKIES': 'true' if https else 'false',
    'BODYOFCHRIST_SECRET_KEY': secrets.token_urlsafe(48),
    'BODYOFCHRIST_TOTP_ENCRYPTION_KEY': base64.urlsafe_b64encode(os.urandom(32)).decode(),
    'BODYOFCHRIST_DB_PASSWORD': key(),
    'BODYOFCHRIST_ALLOWED_HOSTS': f'{domain},localhost,127.0.0.1' if https else 'localhost,127.0.0.1',
    'BODYOFCHRIST_SECURE_COOKIES': 'True' if https else 'False',
    'BODYOFCHRIST_CSRF_TRUSTED_ORIGINS': url,
    'BODYOFCHRIST_SUPER_ADMIN_EMAIL': admin,
}
text = open('.env.example', encoding='utf-8').read()
for name, value in values.items():
    text, n = re.subn(rf'^{name}=.*$', f'{name}={value}', text, count=1, flags=re.M)
    if not n: text += f'\n{name}={value}\n'
old = os.umask(0o077)
open('.env', 'w', encoding='utf-8').write(text)
os.umask(old)
PY
chmod 600 .env
echo "Created .env (readable only by you)."
echo "Still to fill in by hand when you have them: OPENAI_API_KEY, ANTHROPIC_API_KEY, mail (SMTP), Stripe, Google."
echo "Body of Christ: set COMPOSE_PROFILES=bodyofchrist once its image exists, after: docker login ghcr.io"
echo "Keep a copy of .env in your password manager — without it the databases cannot be opened."
