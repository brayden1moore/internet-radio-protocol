import sys
import sqlite3
from pathlib import Path
from collections import Counter

import genres

DB_PATH = Path(__file__).parent / "plays.db"


def ensure_columns(conn):
    """Add category / categories columns if missing. Returns list of added names."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(plays)")}
    added = []
    if "category" not in cols:
        conn.execute("ALTER TABLE plays ADD COLUMN category TEXT")
        added.append("category")
    if "categories" not in cols:
        conn.execute("ALTER TABLE plays ADD COLUMN categories TEXT")
        added.append("categories")
    if added:
        conn.commit()
    return added


def recompute(conn, commit=True):
    ensure_columns(conn)

    rows = conn.execute(
        "SELECT id, acr_genres, lf_tags, category, categories "
        "FROM plays WHERE matched = 1"
    ).fetchall()

    updates = []
    resolved = empty = 0
    for pid, acr, lf, old_cat, old_cats in rows:
        primary, joined = genres.resolve_row(acr, lf)
        if primary:
            resolved += 1
        else:
            empty += 1
        # Only queue a write if something actually changed.
        if primary != old_cat or joined != old_cats:
            updates.append((primary, joined, pid))

    if updates:
        conn.executemany(
            "UPDATE plays SET category = ?, categories = ? WHERE id = ?", updates
        )
        if commit:
            conn.commit()

    return {
        "changed": len(updates),
        "resolved": resolved,
        "empty": empty,
        "total": len(rows),
    }


def _preview(conn):
    """Dry-run: report what recompute would do, without writing."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(plays)")}
    missing = [c for c in ("category", "categories") if c not in cols]
    if missing:
        print(f"  (dry run) would add columns: {', '.join(missing)}")

    rows = conn.execute(
        "SELECT acr_genres, lf_tags, "
        "       COALESCE(category, '') , COALESCE(categories, '') "
        "FROM plays WHERE matched = 1"
    ).fetchall()

    changed = resolved = empty = 0
    dist = Counter()
    for acr, lf, old_cat, old_cats in rows:
        primary, joined = genres.resolve_row(acr, lf)
        if primary:
            resolved += 1
            dist[primary] += 1
        else:
            empty += 1
        if (primary or "") != old_cat or (joined or "") != old_cats:
            changed += 1

    print(f"{len(rows)} matched rows to resolve")
    print(f"  would change {changed} rows "
          f"({resolved} resolved, {empty} left null)")
    for cat, n in dist.most_common():
        print(f"    {n:5}  {cat}")


def main():
    dry = "--dry-run" in sys.argv
    pos = [a for a in sys.argv[1:] if not a.startswith("--")]
    db = Path(pos[0]) if pos else DB_PATH

    if not db.exists():
        sys.exit(
            f"No database at {db.resolve()}\n"
            f"(cwd is {Path.cwd()}). Pass the real path as an argument, e.g.\n"
            f"    python {Path(__file__).name} /full/path/to/plays.db"
        )

    print(f"Opening {db.resolve()}")
    conn = sqlite3.connect(db)

    if not conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='plays'"
    ).fetchone():
        sys.exit(f"{db.resolve()} has no 'plays' table — wrong database?")

    if dry:
        _preview(conn)
    else:
        stats = recompute(conn)
        print(f"Updated {stats['changed']} changed rows "
              f"({stats['resolved']} resolved, {stats['empty']} null, "
              f"{stats['total']} matched total).")
    conn.close()


if __name__ == "__main__":
    main()