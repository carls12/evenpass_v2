"""Database of the central CMGI account: users, sessions, Pro access and AI credits.

Production: the platform's central PostgreSQL (database "accounts"). Tests and local
development: a SQLite file. SQLAlchemy Core keeps the SQL identical for both.
Schema changes are additive only (new tables/columns), so an older version still runs.
"""
import os
from pathlib import Path

from sqlalchemy import (Boolean, Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text,
                        UniqueConstraint, create_engine, event)

BASE = Path(__file__).resolve().parent
DATABASE_URL = os.getenv('ACCOUNTS_DATABASE_URL', f"sqlite:///{BASE / 'accounts.sqlite3'}")

engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def _sqlite_pragmas(conn, _):
        conn.execute('PRAGMA foreign_keys=ON')

meta = MetaData()
TS = DateTime(timezone=True)

users = Table(
    'users', meta,
    Column('id', String(32), primary_key=True),
    Column('email', String(200), nullable=False, unique=True),  # always lower-case
    Column('name', String(120), nullable=False),
    Column('password_hash', String(300), nullable=False),
    Column('email_verified_at', TS),
    Column('trial_ends_at', TS),          # set when the email is confirmed (one trial per account)
    Column('disabled_at', TS),
    Column('created_at', TS, nullable=False),
    Column('last_login_at', TS),
)

sessions = Table(
    'sessions', meta,
    Column('token_hash', String(64), primary_key=True),  # sha256 of the token; the token itself is never stored
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('created_at', TS, nullable=False),
    Column('expires_at', TS, nullable=False),
    Column('client', String(200), nullable=False, default=''),
)

# One-time links: email confirmation and password reset.
tokens = Table(
    'tokens', meta,
    Column('token_hash', String(64), primary_key=True),
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
    Column('purpose', String(20), nullable=False),  # verify | reset
    Column('expires_at', TS, nullable=False),
    Column('used_at', TS),
)

# Pro given by the platform admin (null "until" = no end date).
pro_grants = Table(
    'pro_grants', meta,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('until', TS),
    Column('note', String(300), nullable=False, default=''),
    Column('granted_by', String(200), nullable=False),
    Column('created_at', TS, nullable=False),
    Column('revoked_at', TS),
)

# Paid Pro (Stripe). One row per user, kept in sync by the payment webhook.
subscriptions = Table(
    'subscriptions', meta,
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('provider', String(20), nullable=False, default='stripe'),
    Column('customer_id', String(100)),
    Column('subscription_id', String(100)),
    Column('status', String(30), nullable=False),  # active | trialing | past_due | canceled | ...
    Column('current_period_end', TS),
    Column('updated_at', TS, nullable=False),
)

# Link between a CMGI account and its Stripe customer (created at the first checkout).
billing_customers = Table(
    'billing_customers', meta,
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
    Column('customer_id', String(100), nullable=False, unique=True),
    Column('created_at', TS, nullable=False),
)

# AI credits as a ledger of seconds: purchases/trial/admin are positive, usage negative.
# "ref" makes every booking idempotent (same transcription or payment is never counted twice).
credit_ledger = Table(
    'credit_ledger', meta,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('seconds', Integer, nullable=False),
    Column('reason', String(30), nullable=False),  # trial | purchase | admin | usage | refund
    Column('ref', String(200), unique=True),
    Column('note', String(300), nullable=False, default=''),
    Column('created_by', String(200), nullable=False, default=''),
    Column('created_at', TS, nullable=False),
)

# Admin actions, so every Pro grant or credit change can be traced.
audit_log = Table(
    'audit_log', meta,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('actor', String(200), nullable=False),
    Column('action', String(50), nullable=False),
    Column('user_id', String(32)),
    Column('detail', Text, nullable=False, default=''),
    Column('created_at', TS, nullable=False),
)


# Sign-in with an outside provider (Google). "subject" is the provider's stable user id.
identities = Table(
    'identities', meta,
    Column('provider', String(20), primary_key=True),
    Column('subject', String(200), primary_key=True),
    Column('user_id', String(32), ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
    Column('email', String(200), nullable=False, default=''),
    Column('created_at', TS, nullable=False),
)


def init():
    meta.create_all(engine)


__all__ = ['engine', 'meta', 'init', 'users', 'sessions', 'tokens', 'pro_grants', 'subscriptions', 'billing_customers',
           'credit_ledger', 'audit_log', 'identities', 'Boolean', 'UniqueConstraint']
