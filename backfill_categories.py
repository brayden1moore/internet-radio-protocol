import sys
import sqlite3
from pathlib import Path
from collections import Counter

import genres

DB_PATH = Path(__file__).parent / "plays.db"


def norm_artist(name):
    """
    artist_tag_cache is keyed on lowercased names; plays.artist keeps whatever
    ACRCloud returned. Normalise both sides at every lookup so the two never
    drift apart again.
    """
    return " ".join((name or "").lower().split())


def load_artist_tags(conn):
    """{normalised artist: tag string}. Artists cached with no tags are skipped."""
    try:
        rows = conn.execute("SELECT artist, tags FROM artist_tag_cache")
    except sqlite3.OperationalError:
        return {}                     # cache table not created yet
    return {norm_artist(a): t for a, t in rows if t}


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


def recompute(conn, commit=True, use_artist_tags=True):
    ensure_columns(conn)
    artist_tags = load_artist_tags(conn) if use_artist_tags else {}

    rows = conn.execute(
        "SELECT id, artist, acr_genres, lf_tags, category, categories "
        "FROM plays WHERE matched = 1"
    ).fetchall()

    updates = []
    resolved = empty = rescued = 0
    for pid, artist, acr, lf, old_cat, old_cats in rows:
        at = artist_tags.get(norm_artist(artist))
        primary, joined = genres.resolve_row(acr, lf, at)
        if primary:
            resolved += 1
            # Did the artist-level tags add anything the track tags could not?
            if at and joined != (genres.resolve_row(acr, lf)[1] or None):
                rescued += 1
        else:
            empty += 1
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
        "rescued": rescued,
        "artists_cached": len(artist_tags),
        "total": len(rows),
    }


def _preview(conn, use_artist_tags=True):
    """Dry-run: report what recompute would do, without writing."""
    cols = {r[1] for r in conn.execute("PRAGMA table_info(plays)")}
    missing = [c for c in ("category", "categories") if c not in cols]
    if missing:
        print(f"  (dry run) would add columns: {', '.join(missing)}")

    artist_tags = load_artist_tags(conn) if use_artist_tags else {}
    print(f"  artist tag cache: {len(artist_tags)} artists with tags")

    rows = conn.execute(
        "SELECT artist, acr_genres, lf_tags, "
        "       COALESCE(category, ''), COALESCE(categories, '') "
        "FROM plays WHERE matched = 1"
    ).fetchall()

    changed = resolved = empty = 0
    dist, moved = Counter(), Counter()
    for artist, acr, lf, old_cat, old_cats in rows:
        at = artist_tags.get(norm_artist(artist))
        primary, joined = genres.resolve_row(acr, lf, at)
        if primary:
            resolved += 1
            dist[primary] += 1
        else:
            empty += 1
        if (primary or "") != old_cat or (joined or "") != old_cats:
            changed += 1
            if old_cat:
                moved[f"{old_cat} -> {primary or '(none)'}"] += 1

    print(f"{len(rows)} matched rows to resolve")
    print(f"  would change {changed} rows "
          f"({resolved} resolved, {empty} left null)")
    print("\n  primary category distribution after:")
    for cat, n in dist.most_common():
        print(f"    {n:6}  {cat}")
    print("\n  biggest primary-category moves:")
    for move, n in moved.most_common(15):
        print(f"    {n:6}  {move}")


def main():
    dry = "--dry-run" in sys.argv
    no_artist = "--no-artist-tags" in sys.argv
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
        sys.exit(f"{db.resolve()} has no 'plays' table -- wrong database?")

    if dry:
        _preview(conn, use_artist_tags=not no_artist)
    else:
        stats = recompute(conn, use_artist_tags=not no_artist)
        print(f"Updated {stats['changed']} changed rows "
              f"({stats['resolved']} resolved, {stats['empty']} null, "
              f"{stats['total']} matched total).")
        if stats["rescued"]:
            print(f"  {stats['rescued']} rows gained categories from the "
                  f"artist tag cache ({stats['artists_cached']} artists)")
    conn.close()


if __name__ == "__main__":
    main()