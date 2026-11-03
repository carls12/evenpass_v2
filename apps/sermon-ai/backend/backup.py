"""Consistent backup of the Sermon Intelligence database and recordings.

  python backup.py              # create a backup, keep the newest 14
  python backup.py --keep 30
"""
import argparse, os, shutil, sqlite3, sys
from datetime import datetime
from pathlib import Path


def backup(db_path: Path, audio_dir: Path, dest_dir: Path) -> Path:
    target = dest_dir / datetime.now().strftime('%Y%m%d-%H%M%S')
    target.mkdir(parents=True)
    src = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    dst = sqlite3.connect(target / 'sermon.sqlite3')
    try:
        src.backup(dst)  # online backup API: safe while the API is running
        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup integrity check failed')
    finally:
        src.close(); dst.close()
    if audio_dir.is_dir():
        shutil.copytree(audio_dir, target / 'audio')
    return target


if __name__ == '__main__':
    base = Path(__file__).resolve().parent
    db = Path(os.getenv('SERMON_DB_PATH', str(base / 'sermon.sqlite3')))
    audio = Path(os.getenv('SERMON_AUDIO_DIR', str(db.parent / 'audio')))
    dest = Path(os.getenv('SERMON_BACKUP_DIR', str(db.parent / 'backups')))
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', type=int, default=14, help='number of backups to keep (0 = keep all)')
    args = ap.parse_args()
    if os.getenv('SERMON_DATABASE_URL'):
        # The database lives in the central PostgreSQL and is dumped by infrastructure/deployment/backup.sh;
        # here only the recordings are saved.
        target = dest / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-audio')
        target.mkdir(parents=True)
        if audio.is_dir():
            shutil.copytree(audio, target / 'audio')
        (target / 'DATABASE.txt').write_text('Database: central PostgreSQL, see postgres-sermon-*.dump')
        for old in (sorted(dest.glob('*-audio'))[:-args.keep] if args.keep > 0 else []):
            shutil.rmtree(old)
        sys.exit(print(f'Backup created: {target} (recordings; database dumped separately)'))
    if not db.exists():
        sys.exit(f'Database not found: {db}')
    result = backup(db, audio, dest)
    if args.keep > 0:
        for old in sorted(p for p in dest.iterdir() if (p / 'sermon.sqlite3').exists())[:-args.keep]:
            shutil.rmtree(old)
    print(f'Backup created: {result}')
