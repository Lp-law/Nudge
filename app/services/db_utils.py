"""SQLite connection helpers with WAL mode and busy timeout."""

import sqlite3
import threading
from contextlib import contextmanager

_write_lock = threading.Lock()


@contextmanager
def sqlite_connect(db_path: str, *, readonly: bool = False):
    """Open a SQLite connection with WAL mode and serialized writes.

    Parameters
    ----------
    db_path:
        Filesystem path to the SQLite database file.
    readonly:
        When *True* the caller only reads; the global write-lock is
        **not** acquired and no implicit commit is performed.
    """
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        if readonly:
            yield conn
        else:
            with _write_lock:
                yield conn
                conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
