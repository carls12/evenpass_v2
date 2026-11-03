"""One database layer for SQLite (local development, tests) and the central PostgreSQL (server).

The app keeps writing plain SQL with "?" placeholders, as it did for SQLite. On PostgreSQL:
- placeholders and a few SQLite-only constructs are translated (GROUP_CONCAT, AUTOINCREMENT),
- rows behave like sqlite3.Row (row['name'], row[0], dict(row)),
- every statement runs in its own savepoint, so a failed INSERT (e.g. a duplicate) does not
  abort the whole request — the same behaviour the code relies on with SQLite.
"""
import re
import sqlite3
from contextlib import contextmanager
from decimal import Decimal

try:
    import psycopg
except ImportError:  # SQLite-only installations
    psycopg = None

IntegrityError = (sqlite3.IntegrityError,) + ((psycopg.IntegrityError,) if psycopg else ())


def is_postgres(target) -> bool:
    return isinstance(target, str) and target.startswith(('postgres://', 'postgresql://'))


class Row(dict):
    """dict with positional access, like sqlite3.Row."""
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return dict.__getitem__(self, key)


def _value(v):
    return int(v) if isinstance(v, Decimal) and v == v.to_integral_value() else v  # SUM() returns numeric


def _row_factory(cursor):
    names = [d.name for d in cursor.description] if cursor.description else []
    return lambda values: Row(zip(names, map(_value, values)))


_GROUP_CONCAT_SEP = re.compile(r"GROUP_CONCAT\(\s*([^(),]+?)\s*,\s*('[^']*')\s*\)", re.I)
_GROUP_CONCAT = re.compile(r"GROUP_CONCAT\(\s*([^(),]+?)\s*\)", re.I)


def translate(sql: str) -> str:
    sql = _GROUP_CONCAT_SEP.sub(r'string_agg(\1, \2)', sql)
    sql = _GROUP_CONCAT.sub(r"string_agg(\1, ',')", sql)
    sql = re.sub(r'INTEGER PRIMARY KEY AUTOINCREMENT', 'BIGSERIAL PRIMARY KEY', sql, flags=re.I)
    return sql.replace('%', '%%').replace('?', '%s')


class PgConnection:
    def __init__(self, conn):
        self.conn = conn
        self._savepoints = 0

    def execute(self, sql, params=()):
        self._savepoints += 1
        name = f'sp{self._savepoints}'
        self.conn.execute(f'SAVEPOINT {name}')
        cursor = self.conn.cursor(row_factory=_row_factory)
        try:
            cursor.execute(translate(sql), tuple(params))
        except Exception:
            self.conn.execute(f'ROLLBACK TO SAVEPOINT {name}')
            raise
        self.conn.execute(f'RELEASE SAVEPOINT {name}')
        return cursor

    def executescript(self, script: str):
        for statement in script.split(';'):
            if statement.strip():
                self.execute(statement)


@contextmanager
def connect(target):
    """target: a PostgreSQL URL or the path of a SQLite file."""
    if is_postgres(target):
        if psycopg is None:
            raise RuntimeError('PostgreSQL configured but psycopg is not installed')
        conn = psycopg.connect(target, connect_timeout=10)
        try:
            yield PgConnection(conn)
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()
        return
    conn = sqlite3.connect(target, timeout=20)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA busy_timeout=20000')
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def table_exists(c, table: str) -> bool:
    if isinstance(c, PgConnection):
        return c.execute("SELECT 1 FROM information_schema.tables WHERE table_schema=current_schema() AND table_name=?", (table,)).fetchone() is not None
    return c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone() is not None


def columns(c, table: str) -> set:
    if isinstance(c, PgConnection):
        return {r[0] for r in c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name=?", (table,))}
    return {r[1] for r in c.execute(f'PRAGMA table_info({table})')}


def copy_from_sqlite(sqlite_path, c, tables, serial=()):
    """One-time import of an existing SQLite database into an EMPTY PostgreSQL database.

    tables: in foreign-key order. serial: tables whose integer "id" sequence must continue after
    the copied rows. Row counts are compared afterwards; any difference aborts (and rolls back).
    The SQLite file is only read, never changed — it stays as a fallback.
    """
    src = sqlite3.connect(f'file:{sqlite_path}?mode=ro', uri=True)
    src.row_factory = sqlite3.Row
    copied = {}
    try:
        present = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table in tables:
            if table not in present:
                continue
            target_cols = columns(c, table)
            rows = src.execute(f'SELECT * FROM {table}').fetchall()
            for row in rows:
                cols = [k for k in row.keys() if k in target_cols]
                c.execute(f"INSERT INTO {table}({','.join(cols)}) VALUES ({','.join('?' * len(cols))})", [row[k] for k in cols])
            copied[table] = len(rows)
        for table, count in copied.items():
            now = c.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]
            if now != count:
                raise RuntimeError(f'Import check failed for {table}: {count} rows in SQLite, {now} in PostgreSQL')
        for table in serial:
            if copied.get(table):
                c.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))")
    finally:
        src.close()
    return copied
