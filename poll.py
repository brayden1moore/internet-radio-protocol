import os
import sys
import time
import hmac
import json
import base64
import sqlite3
import hashlib
import requests
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import genres
import backfill_categories
from artist_tags import ensure_cache, artist_top_tags

try:
    with open('environ.json','r') as f:
        env = json.load(f)
        ACR_HOST = env.get('ACR_HOST')
        ACR_KEY = env.get('ACR_KEY')
        ACR_SECRET = env.get('ACR_SECRET')
        LASTFM_KEY = env.get('LASTFM_KEY')
except:
    ACR_HOST = os.environ.get('ACR_HOST')
    ACR_KEY = os.environ.get('ACR_KEY')
    ACR_SECRET = os.environ.get('ACR_SECRET')
    LASTFM_KEY = os.environ.get('LASTFM_KEY')

CAPTURE_SECONDS = 12
MAX_BYTES = 1_000_000
UA = "oneradio/0.1 ( brayden@one.radio )"
DB_PATH = Path(__file__).parent / "plays.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS plays (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT NOT NULL,            -- ISO8601 UTC, when we polled
    station       TEXT NOT NULL,            -- station key/name
    source        TEXT NOT NULL,            -- 'selfreport' | 'acrcloud' | 'acrcloud_nomatch'
    matched       INTEGER NOT NULL,         -- 1 if a track was identified, else 0
    artist        TEXT,
    title         TEXT,
    -- ACRCloud metadata
    acr_genres    TEXT,                     -- comma-joined
    acr_release   TEXT,                     -- release_date, e.g. '2001-10-23'
    acr_label     TEXT,
    -- Last.fm popularity
    lf_playcount  INTEGER,
    lf_listeners  INTEGER,
    lf_tags       TEXT,                     -- comma-joined community tags
    lf_tags       TEXT,                     -- comma-joined community tags
    -- Consolidated categories
    category      TEXT,                     -- primary consolidated category
    categories    TEXT, 
    -- MusicBrainz metadata (optional)
    mb_genre      TEXT,
    mb_year       INTEGER
);
CREATE INDEX IF NOT EXISTS idx_plays_station ON plays(station);
CREATE INDEX IF NOT EXISTS idx_plays_ts ON plays(ts);
CREATE INDEX IF NOT EXISTS idx_plays_matched ON plays(matched);
"""

def utcnow():
    return datetime.now(timezone.utc).isoformat()

# --------------------------------------------------------------------------
# Identification
# --------------------------------------------------------------------------
def capture(url, seconds):
    cmd = [
        "ffmpeg",
        "-nostdin",
        "-loglevel", "error",
        "-user_agent", "Mozilla/5.0",
        "-i", url,
        "-t", str(seconds),     
        "-vn",                 
        "-ac", "1",            
        "-ar", "44100",
        "-b:a", "128k",
        "-f", "mp3",
        "pipe:1",              
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, timeout=seconds + 30
        )
    except subprocess.TimeoutExpired:
        return b""
    if proc.returncode != 0:
        # ffmpeg couldn't open/decode the stream
        return b""
    return proc.stdout

def acr_identify(sample):
    ts = str(time.time())
    string_to_sign = "\n".join(["POST", "/v1/identify", ACR_KEY, "audio", "1", ts])
    sign = base64.b64encode(
        hmac.new(ACR_SECRET.encode(), string_to_sign.encode(), hashlib.sha1).digest()
    ).decode()
    files = {"sample": ("s.mp3", sample, "audio/mpeg")}
    data = {
        "access_key": ACR_KEY, "sample_bytes": len(sample), "timestamp": ts,
        "signature": sign, "data_type": "audio", "signature_version": "1",
    }
    r = requests.post(f"https://{ACR_HOST}/v1/identify", files=files, data=data, timeout=30)
    payload = r.json()
    if payload.get("status", {}).get("code") != 0:
        return None
    music = payload.get("metadata", {}).get("music", [])
    if not music:
        return None
    top = music[0]
    return {
        "artist": ", ".join(a["name"] for a in top.get("artists", [])),
        "title": top.get("title", ""),
        "acr_genres": ", ".join(g["name"] for g in top.get("genres", [])),
        "acr_release": top.get("release_date"),
        "acr_label": top.get("label"),
    }


def identify(station):
    status = (station.get("status") or "").lower()
    if status == "offline" or station.get("hidden") is True:
        return None  # only truly dead/hidden stations are skipped

    # --- 1. Self-report fast path ---
    sr_title = (station.get("nowPlaying") or "").strip()
    sr_artist = (station.get("nowPlayingArtist") or "").strip()
    if station.get("songBasis") and sr_title and sr_artist:
        lf = lastfm(sr_artist, sr_title)
        if lf:
            return {
                "matched": True,
                "source": "selfreport",
                "artist": sr_artist,
                "title": sr_title,
                "acr_genres": None,
                "acr_release": None,
                "acr_label": None,
                "lf": lf,  
            }

    # --- 2/3. ACR fingerprint path ---
    url = station.get("streamLink")
    if not url:
        return None
    try:
        sample = capture(url, CAPTURE_SECONDS)
    except Exception as e:
        print(f"    capture error: {e!r}")
        return None
    if len(sample) < 10_000:
        print(f"    capture too small ({len(sample)}B)")
        return None

    acr = acr_identify(sample)
    if not acr or not acr.get("title"):
        # Live stream, but no recognizable track. Still worth logging: might be talk, an obscure record, or something too rare for ACR's database.
        return {"matched": False}
    acr["matched"] = True
    acr["source"] = "acrcloud"
    acr["lf"] = None  
    return acr


# --------------------------------------------------------------------------
# Enrichment
# --------------------------------------------------------------------------
def lastfm(artist, title):
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={
                "method": "track.getInfo", "api_key": LASTFM_KEY,
                "artist": artist, "track": title,
                "autocorrect": 1, "format": "json",
            },
            headers={"User-Agent": UA}, timeout=30,
        )
        data = r.json()
    except Exception:
        return None
    if "track" not in data:
        return None
    t = data["track"]
    tags = [tag["name"] for tag in t.get("toptags", {}).get("tag", [])]
    return {
        "playcount": int(t.get("playcount", 0)),
        "listeners": int(t.get("listeners", 0)),
        "tags": tags,
    }


def musicbrainz(artist, title):
    try:
        r = requests.get(
            "https://musicbrainz.org/ws/2/recording",
            params={
                "query": f'recording:"{title}" AND artist:"{artist}"',
                "limit": 1, "inc": "genres+releases", "fmt": "json",
            },
            headers={"User-Agent": UA}, timeout=30,
        )
        if r.status_code != 200:
            return None
        recs = r.json().get("recordings", [])
    except Exception:
        return None
    if not recs:
        return None
    rec = recs[0]
    genres = [g["name"] for g in rec.get("genres", [])]
    year = None
    for rel in rec.get("releases", []):
        d = rel.get("date", "")
        if len(d) >= 4 and d[:4].isdigit():
            y = int(d[:4])
            year = y if year is None else min(year, y)
    return {"genre": genres[0] if genres else None, "year": year}


# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_mb = "--no-mb" not in sys.argv
    if not args:
        stations = requests.get('https://one.radio/info').json()
    else:
        stations = json.loads(Path(args[0]).read_text())

    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)
    ensure_cache(conn)

    # pull in any category changes
    stats = backfill_categories.recompute(conn)
    if stats["changed"]:
        print(f"  recategorized {stats['changed']} rows to current mapping")

    matched = nomatch = skipped = 0
    for key, st in stations.items():
        name = st.get("name", key)
        print(name)
        track = identify(st)

        if track is None:
            skipped += 1
            print(f"[skip] {name} (status={st.get('status')}, hidden={st.get('hidden')})")
            continue

        if not track.get("matched"):
            # Live but unidentified 
            conn.execute(
                "INSERT INTO plays (ts, station, source, matched) VALUES (?,?,?,0)",
                (utcnow(), name, "acrcloud_nomatch"),
            )
            conn.commit()
            nomatch += 1
            print(f"[miss] {name}: live, no ACR match (logged)")
            continue

        # Reuse Last.fm result 
        lf = track.get("lf")
        if lf is None:
            lf = lastfm(track["artist"], track["title"])

        # Genre fallback 
        have_acr   = bool(track.get("acr_genres"))
        have_lftag = bool(lf and lf.get("tags"))
        lf_tags_out = ", ".join(lf["tags"][:5]) if have_lftag else None
        if not have_acr and not have_lftag:
            at = artist_top_tags(track["artist"], conn, LASTFM_KEY)
            if at:
                lf_tags_out = at

        # Consolidated categories (same resolver as the backfill).
        category, categories = genres.resolve_row(track.get("acr_genres"), lf_tags_out)

        mb = musicbrainz(track["artist"], track["title"]) if use_mb else None
        if use_mb:
            time.sleep(1.1)  # MusicBrainz ~1 req/s

        conn.execute(
            "INSERT INTO plays (ts, station, source, matched, artist, title,"
            " acr_genres, acr_release, acr_label,"
            " lf_playcount, lf_listeners, lf_tags, mb_genre, mb_year, category, categories)"
            " VALUES (?,?,?,1,?,?,?,?,?,?,?,?,?,?)",
            (
                utcnow(), name, track["source"], track["artist"], track["title"],
                track.get("acr_genres"), track.get("acr_release"), track.get("acr_label"),
                lf["playcount"] if lf else None,
                lf["listeners"] if lf else None,
                lf_tags_out,
                mb["genre"] if mb else None,
                mb["year"] if mb else None,
                category, 
                categories,
            ),
        )
        conn.commit()
        matched += 1
        pop = f"{lf['playcount']:,} plays" if lf else "no last.fm"
        genre = track.get("acr_genres") or (", ".join(lf["tags"][:3]) if lf and lf["tags"] else "?")
        print(f"[log ] {name} ({track['source']}): {track['artist']} - {track['title']}  [{genre}; {pop}]")

    conn.close()
    print(f"\nDone. {matched} matched, {nomatch} no-match, {skipped} skipped -> {DB_PATH}")


if __name__ == "__main__":
    main()