import time
import requests

UA = "oneradio/0.1 ( brayden@one.radio )"

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS artist_tag_cache (
    artist   TEXT PRIMARY KEY,   -- lowercased artist name (cache key)
    tags     TEXT,               -- comma-joined tags, or '' if none found
    fetched  TEXT                -- ISO8601 UTC of the fetch
);
"""

def ensure_cache(conn):
    conn.executescript(CACHE_SCHEMA)
    conn.commit()


def _cache_key(artist):
    # First credited artist only
    return artist.split(",")[0].strip().lower()


def artist_top_tags(artist, conn, lastfm_key, limit=5, min_weight=10, sleep=0.25):
    if not artist:
        return None
    key = _cache_key(artist)
    if not key:
        return None

    row = conn.execute(
        "SELECT tags FROM artist_tag_cache WHERE artist = ?", (key,)
    ).fetchone()
    if row is not None:
        return row[0] or None 

    tags = _fetch(key, lastfm_key, limit, min_weight)
    conn.execute(
        "INSERT OR REPLACE INTO artist_tag_cache (artist, tags, fetched) "
        "VALUES (?,?,?)",
        (key, tags or "", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
    )
    conn.commit()
    time.sleep(sleep)
    return tags


def _fetch(artist, lastfm_key, limit, min_weight):
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "artist.getTopTags", "api_key": lastfm_key,
                "artist": artist, "autocorrect": 1, "format": "json",
            },
            headers={"User-Agent": UA}, timeout=30,
        )
        data = r.json()
    except Exception:
        return None
    raw = data.get("toptags", {}).get("tag", [])
    if not raw:
        return None
    kept = []
    for t in raw:
        try:
            w = int(t.get("count", 0))
        except (TypeError, ValueError):
            w = 0
        if w >= min_weight:
            kept.append(t["name"])
        if len(kept) >= limit:
            break
    return ", ".join(kept) if kept else None