"""
Repair ACRCloud rows stored as mojibake ("L'Ã©colier" -> "L'écolier").

poll.py used to read ACR's response with requests' r.json(), which decoded the
UTF-8 body as ISO-8859-1. Those rows also mostly missed on Last.fm (and
MusicBrainz) because the lookup used the garbled names, so this re-enriches
them after fixing the text, then recategorizes and rebuilds the rollups.

    python fix_mojibake.py              # dry run: counts + examples, writes nothing
    python fix_mojibake.py --apply      # fix text + re-query Last.fm
    python fix_mojibake.py --apply --mb # ...and MusicBrainz too (~1 req/s, slow)
"""
import sys
import time
import sqlite3

import poll
import station_stats
import backfill_categories

TEXT_COLS = ("artist", "title", "acr_label", "acr_genres")


def repair(s):
    """Undo one round of UTF-8-read-as-Latin-1. Returns s unchanged if it isn't that."""
    if not s:
        return s
    try:
        fixed = s.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return s          # has chars outside Latin-1, or isn't valid UTF-8 underneath
    return fixed


def main():
    apply = "--apply" in sys.argv
    use_mb = "--mb" in sys.argv
    conn = sqlite3.connect(poll.DB_PATH)

    rows = conn.execute(
        f"SELECT id, {', '.join(TEXT_COLS)}, lf_playcount, mb_year FROM plays"
        "  WHERE source = 'acrcloud'"
    ).fetchall()

    todo = []
    for pid, *vals, lf_playcount, mb_year in rows:
        fixed = [repair(v) for v in vals]
        if fixed != vals:
            todo.append((pid, vals, fixed, lf_playcount, mb_year))

    print(f"{len(todo):,} of {len(rows):,} acrcloud rows need repair")
    for _, old, new, *_ in todo[:10]:
        print(f"  {old[0]} — {old[1]}\n    -> {new[0]} — {new[1]}")
    if not apply:
        print("\nDry run. Re-run with --apply to write.")
        return

    relooked = found = 0
    lf_cache, mb_cache = {}, {}
    for i, (pid, old, new, lf_playcount, mb_year) in enumerate(todo, 1):
        artist, title, label, acr_genres = new
        conn.execute(
            "UPDATE plays SET artist=?, title=?, acr_label=?, acr_genres=? WHERE id=?",
            (artist, title, label, acr_genres, pid),
        )

        key = (artist.lower(), title.lower())
        if lf_playcount is None:
            if key not in lf_cache:
                lf_cache[key] = poll.lastfm(artist, title)
                time.sleep(0.25)
            lf = lf_cache[key]
            relooked += 1
            if lf:
                found += 1
                conn.execute(
                    "UPDATE plays SET lf_playcount=?, lf_listeners=?, lf_tags=COALESCE(?, lf_tags)"
                    " WHERE id=?",
                    (lf["playcount"], lf["listeners"],
                     ", ".join(lf["tags"][:5]) if lf["tags"] else None, pid),
                )

        if use_mb and mb_year is None:
            if key not in mb_cache:
                mb_cache[key] = poll.musicbrainz(artist, title)
                time.sleep(1.1)
            mb = mb_cache[key]
            if mb:
                conn.execute("UPDATE plays SET mb_genre=COALESCE(mb_genre, ?), mb_year=? WHERE id=?",
                             (mb["genre"], mb["year"], pid))

        if i % 100 == 0:
            conn.commit()
            print(f"  {i:,}/{len(todo):,}  (Last.fm found {found}/{relooked})")
    conn.commit()
    print(f"Repaired {len(todo):,} rows; Last.fm now found for {found:,} of {relooked:,} re-checked.")

    stats = backfill_categories.recompute(conn)
    print(f"Recategorized {stats.get('changed', 0):,} rows")
    roll = station_stats.recompute(conn)
    print(f"Rolled up {roll['stations']} stations")
    conn.close()


if __name__ == "__main__":
    main()
