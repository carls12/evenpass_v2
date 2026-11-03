"""Consistent backups of the EventPass database and uploaded badge images.

Uses SQLite's online backup API, so it is safe while the API is running.

  python backup.py                      # create a backup, keep the newest 30
  python backup.py --keep 14            # custom retention
  python backup.py --restore <folder>   # restore a backup (backs up the current state first)
  python backup.py --restore old.sqlite3  # import a single database file the same way
  python backup.py --list
"""
import argparse, os, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path

TABLES = ('events', 'participants', 'checkins', 'gate_users')


def counts(db_path):
    conn = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        return {t: conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0] for t in TABLES if t in names}
    finally:
        conn.close()


def backup_database(db_path, dest_dir, assets_dir=None, label='manual'):
    db_path, dest_dir = Path(db_path), Path(dest_dir)
    if not db_path.exists():
        return None
    target = dest_dir / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{label}"
    suffix = 1
    while target.exists():
        target = target.with_name(f'{target.name}-{suffix}'); suffix += 1
    target.mkdir(parents=True)
    src = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    dst = sqlite3.connect(target / 'eventpass.sqlite3')
    try:
        src.backup(dst)
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError(f'Backup integrity check failed: {target}')
    finally:
        src.close(); dst.close()
    if counts(db_path) != counts(target / 'eventpass.sqlite3'):
        raise RuntimeError(f'Backup row counts differ from source: {target}')
    if assets_dir and Path(assets_dir).is_dir():
        shutil.copytree(assets_dir, target / 'badge_assets')
    return target


def prune(dest_dir, keep):
    folders = sorted((p for p in Path(dest_dir).glob('*') if (p / 'eventpass.sqlite3').exists()), key=lambda p: p.name)
    for old in folders[:-keep] if keep > 0 else []:
        shutil.rmtree(old)


def restore(snapshot, db_path, assets_dir, dest_dir):
    """Restore a backup folder, or a single .sqlite3 file (e.g. importing an existing local database)."""
    snapshot = Path(snapshot)
    source = snapshot if snapshot.is_file() else snapshot / 'eventpass.sqlite3'
    if not source.exists():
        raise SystemExit(f'No database found at {source}')
    conn = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise SystemExit(f'{source} failed the integrity check — nothing was changed')
    finally:
        conn.close()
    safety = backup_database(db_path, dest_dir, assets_dir, label='pre-restore')
    print(f'Current state saved to {safety}')
    src = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
    dst = sqlite3.connect(db_path)
    try:
        src.backup(dst)  # page-level copy through SQLite, safe with WAL and open readers
    finally:
        src.close(); dst.close()
    if snapshot.is_dir() and (snapshot / 'badge_assets').is_dir():
        shutil.copytree(snapshot / 'badge_assets', assets_dir, dirs_exist_ok=True)
    print(f'Restored {snapshot} -> {db_path}: {counts(db_path)}')


if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    db = Path(os.getenv('EVENTPASS_DB_PATH', str(base / 'eventpass.sqlite3')))
    assets = Path(os.getenv('EVENTPASS_ASSETS_DIR', str(base / 'badge_assets')))
    dest = Path(os.getenv('EVENTPASS_BACKUP_DIR', str(db.parent / 'backups')))
    ap = argparse.ArgumentParser(description='EventPass backup / restore')
    ap.add_argument('--keep', type=int, default=30, help='number of backups to keep (0 = keep all)')
    ap.add_argument('--restore', metavar='FOLDER_OR_FILE')
    ap.add_argument('--list', action='store_true')
    args = ap.parse_args()
    if args.list:
        for p in sorted(dest.glob('*')):
            if (p / 'eventpass.sqlite3').exists(): print(p.name, counts(p / 'eventpass.sqlite3'))
    elif args.restore:
        restore(args.restore, db, assets, dest)
    elif os.getenv('EVENTPASS_DATABASE_URL'):
        # The database lives in the central PostgreSQL and is dumped by infrastructure/deployment/backup.sh;
        # here only the uploaded badge images are saved.
        target = dest / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-assets"
        target.mkdir(parents=True)
        if assets.is_dir(): shutil.copytree(assets, target / 'badge_assets')
        (target / 'DATABASE.txt').write_text('Database: central PostgreSQL, see postgres-eventpass-*.dump')
        for old in sorted(p for p in dest.glob('*-assets'))[:-args.keep] if args.keep > 0 else []: shutil.rmtree(old)
        print(f'Backup created: {target} (badge images; database dumped separately)')
    else:
        result = backup_database(db, dest, assets)
        if result is None: sys.exit(f'Database not found: {db}')
        prune(dest, args.keep)
        print(f'Backup created: {result} {counts(result / "eventpass.sqlite3")}')
