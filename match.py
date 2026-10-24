"""
"Find your radio match": profile a listener from their Last.fm history on the
same scales as the station DNA (genre mix, median release year, obscurity rank)
and score every station with the same weighting the site's You Might Like uses.

    profile = listener_profile(conn, "rj")
    result  = match(conn, dna_payload, profile)

Only public Last.fm data is used, so there's no sign-in: a username is enough.
"""
import os
import json
import math
import time
import sqlite3
import statistics
import threading
import concurrent.futures as cf
from pathlib import Path

import requests

import genres
import station_stats
from artist_tags import ensure_cache, _cache_key, _fetch

UA = "oneradio/0.1 ( brayden@one.radio )"
LF_URL = "https://ws.audioscrobbler.com/2.0/"
TOP_ARTISTS = 50          # artists that shape the genre mix + overlap
TOP_TRACKS = 30           # tracks that shape era + obscurity
WEIGHTS = {"genre": 0.6, "year": 0.2, "obsc": 0.2}   # same as the site's You Might Like
MIN_FOR_YEAR = 5          # need this many dated tracks to use era at all
MIN_FOR_OBSC = 5


class MatchError(Exception):
    """User-facing problem (unknown username, private profile, no history)."""


def _lastfm_key():
    try:
        env = json.loads((Path(__file__).parent / "environ.json").read_text())
        if env.get("LASTFM_KEY"):
            return env["LASTFM_KEY"]
    except Exception:
        pass
    return os.environ.get("LASTFM_KEY")


def lf(method, **params):
    r = requests.get(LF_URL, params={"method": method, "api_key": _lastfm_key(),
                                     "format": "json", **params},
                     headers={"User-Agent": UA}, timeout=20)
    data = r.json()
    if "error" in data:
        raise MatchError(data.get("message") or "Last.fm error")
    return data


def _itunes_year(artist, title):
    """Release year fallback for tracks we've never polled. Free, no key."""
    try:
        r = requests.get("https://itunes.apple.com/search",
                         params={"term": f"{artist} {title}", "entity": "song", "limit": 1},
                         headers={"User-Agent": UA}, timeout=10)
        res = r.json().get("results") or []
        d = res[0].get("releaseDate") if res else None
        return int(d[:4]) if d and d[:4].isdigit() else None
    except Exception:
        return None


# ---------------------------------------------------------------- listener

def listener_profile(conn, username, period="12month"):
    username = (username or "").strip()
    if not username:
        raise MatchError("Enter a Last.fm username.")

    artists = lf("user.gettopartists", user=username, period=period,
                 limit=TOP_ARTISTS).get("topartists", {}).get("artist", [])
    if not artists and period != "overall":
        return listener_profile(conn, username, "overall")
    if not artists:
        raise MatchError("That Last.fm account doesn't have any listening history yet.")
    tracks = lf("user.gettoptracks", user=username, period=period,
                limit=TOP_TRACKS).get("toptracks", {}).get("track", [])

    top = [(a["name"], int(a.get("playcount") or 0)) for a in artists if a.get("name")]

    # ---- genre mix: each artist's Last.fm tags, weighted by how much they listen
    ensure_cache(conn)
    key = _lastfm_key()
    cached = {}
    for name, _ in top:
        row = conn.execute("SELECT tags FROM artist_tag_cache WHERE artist = ?",
                           (_cache_key(name),)).fetchone()
        if row is not None:
            cached[name] = row[0] or None
    missing = [n for n, _ in top if n not in cached]
    if missing:
        with cf.ThreadPoolExecutor(5) as ex:
            for name, tags in zip(missing, ex.map(lambda n: _fetch(_cache_key(n), key, 5, 10), missing)):
                cached[name] = tags
                conn.execute("INSERT OR REPLACE INTO artist_tag_cache (artist, tags, fetched) VALUES (?,?,?)",
                             (_cache_key(name), tags or "", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())))
        conn.commit()

    axis = genres.all_categories()
    weights = dict.fromkeys(axis, 0.0)
    for name, plays in top:
        cats = genres.resolve_categories(None, cached.get(name)) if cached.get(name) else []
        cats = [c for c in cats if c in weights]
        if not cats:
            continue
        w = math.log10(plays + 1) + 1
        for c in cats:
            weights[c] += w / len(cats)
    tot = sum(weights.values())
    genre_vec = [round(100 * weights[c] / tot, 2) if tot else 0.0 for c in axis]

    # ---- era + obscurity from their top tracks
    track_list = [(t["artist"]["name"] if isinstance(t.get("artist"), dict) else t.get("artist"), t.get("name"))
                  for t in tracks if t.get("name")]
    track_list = [(a, t) for a, t in track_list if a and t]

    def known_year(a, t):
        row = conn.execute(
            "SELECT acr_release, mb_year FROM plays WHERE matched = 1"
            " AND LOWER(TRIM(artist)) = ? AND LOWER(TRIM(title)) = ? LIMIT 1",
            (a.strip().lower(), t.strip().lower())).fetchone()
        return station_stats.parse_year(*row) if row else None

    def track_info(at):
        a, t = at
        try:
            info = lf("track.getInfo", artist=a, track=t, autocorrect=1).get("track", {})
            pc = int(info.get("playcount") or 0)
        except Exception:
            pc = None
        return pc

    years = [known_year(a, t) for a, t in track_list]
    with cf.ThreadPoolExecutor(5) as ex:
        playcounts = list(ex.map(track_info, track_list))
        need = [i for i, y in enumerate(years) if y is None][:15]
        for i, y in zip(need, ex.map(lambda i: _itunes_year(*track_list[i]), need)):
            years[i] = y
    this_year = time.gmtime().tm_year
    years = [y for y in years if y and 1900 < y <= this_year]
    playcounts = [p for p in playcounts if p is not None]

    year_median = round(statistics.median(years)) if len(years) >= MIN_FOR_YEAR else None

    return {
        "user": username,
        "top_artists": [n for n, _ in top],
        "genres": genre_vec,
        "categories": axis,
        "year_median": year_median,
        "depth": _track_depth(conn, playcounts) if len(playcounts) >= MIN_FOR_OBSC else None,
    }


# ---------------------------------------------------------------- stations

_artist_cache = {"ver": None, "val": None}
_artist_lock = threading.Lock()


def station_artists(conn):
    """{station: set of lead artists (lowercased)} from the poll log."""
    ver = station_stats.version(conn)
    with _artist_lock:
        if _artist_cache["ver"] == ver:
            return _artist_cache["val"]
    out = {}
    for station, artist in conn.execute("SELECT station, artist FROM plays WHERE matched = 1 AND artist IS NOT NULL"):
        lead = station_stats.fix_text(station_stats._primary_artist(artist)).lower()
        if lead:
            out.setdefault(station, set()).add(lead)
    with _artist_lock:
        _artist_cache.update(ver=ver, val=out)
    return out


_ref_cache = {"ver": None, "val": None}


def _reference(conn):
    """The pool every identified track is ranked against (same as station_stats)."""
    ver = station_stats.version(conn)
    if _ref_cache["ver"] == ver:
        return _ref_cache["val"]
    seen = {}
    for artist, title, plays in conn.execute(
        "SELECT artist, title, lf_playcount FROM plays WHERE matched = 1"
    ):
        key = ((artist or "").strip().lower(), (title or "").strip().lower())
        if key != ("", "") and key not in seen:
            seen[key] = station_stats._play_score(plays)
    ref = sorted(seen.values())
    _ref_cache.update(ver=ver, val=ref)
    return ref


def _track_depth(conn, playcounts):
    """
    Listener's mean per-track obscurity, 0-100, on the same track scale as each
    station's obsc_track_mean. (Station obscurity *rank* counts unidentified polls
    as 0 plays, which a listener's own history never has, so matching uses the
    track scale to compare like with like.)
    """
    ref = _reference(conn)
    vals = [station_stats._track_obscurity(ref, station_stats._play_score(p)) for p in playcounts]
    vals = [v for v in vals if v is not None]
    return statistics.mean(vals) if vals else None


def match(conn, dna, profile):
    radar, spectra, totals = dna["radar"], dna["spectra"], dna["totals"]
    names = [s for s in radar if (totals.get(s) or 0) >= station_stats.MIN_CATEGORIZED]
    if not names:
        raise MatchError("No station data yet.")

    def gdist(a, b):
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    g_max = max((gdist(radar[a], radar[b]) for i, a in enumerate(names) for b in names[i + 1:]), default=1) or 1
    vals = lambda k: [spectra[s][k] for s in names if spectra.get(s, {}).get(k) is not None]
    rng = lambda v: (max(v) - min(v)) if v else 0
    y_scale, o_scale = rng(vals("year_mean")) or 1, rng(vals("obsc_track_mean")) or 1

    me_year = profile["year_median"]
    me_obsc = profile["depth"]
    # for display: share of stations whose typical track is more familiar than yours
    depths = sorted(vals("obsc_track_mean"))
    deeper_than = (round(100 * sum(1 for v in depths if v < me_obsc) / len(depths))
                   if me_obsc is not None and depths else None)
    mine = {a.lower() for a in profile["top_artists"]}
    display = {a.lower(): a for a in profile["top_artists"]}
    played = station_artists(conn)

    scored = []
    for s in names:
        sp = spectra.get(s, {})
        g = gdist(profile["genres"], radar[s]) / g_max
        parts = [(WEIGHTS["genre"], g)]
        y = o = None
        if me_year is not None and sp.get("year_mean") is not None:
            y = abs(me_year - sp["year_mean"]) / y_scale
            parts.append((WEIGHTS["year"], y))
        if me_obsc is not None and sp.get("obsc_track_mean") is not None:
            o = abs(me_obsc - sp["obsc_track_mean"]) / o_scale
            parts.append((WEIGHTS["obsc"], o))
        wsum = sum(w for w, _ in parts)
        d = math.sqrt(sum(w * v * v for w, v in parts) / wsum)
        shared = sorted(mine & played.get(s, set()),
                        key=lambda a: profile["top_artists"].index(display[a]))
        scored.append({
            "station": s, "d": d, "pct": max(0, round(100 * (1 - d))),
            "shared": [display[a] for a in shared], "n_shared": len(shared),
            "_g": g, "_eo": math.sqrt(((y or 0) ** 2 + (o or 0) ** 2) / 2),
        })

    scored.sort(key=lambda x: (x["d"], -x["n_shared"]))
    # stretch: same era + depth, different sound (genre in the far half)
    far = sorted(scored, key=lambda x: x["_g"])[len(scored) // 2:]
    stretch = sorted(far, key=lambda x: x["_eo"])[:12]
    most_shared = sorted(scored, key=lambda x: (-x["n_shared"], x["d"]))[:12]

    clean = lambda xs: [{k: v for k, v in x.items() if not k.startswith("_") and k != "d"} for x in xs]
    axis = profile["categories"]
    top_genres = [axis[i] for i in sorted(range(len(axis)), key=lambda i: -profile["genres"][i])[:3]
                  if profile["genres"][i] > 0]
    return {
        "user": profile["user"],
        "profile": {"top_genres": top_genres, "year_median": me_year, "deeper_than": deeper_than,
                    "genres": profile["genres"], "categories": axis},
        # a dozen of each so the page can skip stations it doesn't list
        "matches": clean(scored[:12]),
        "stretch": clean(stretch),
        "most_shared": clean([x for x in most_shared if x["n_shared"]]),
    }
