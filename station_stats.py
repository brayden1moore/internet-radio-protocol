import math
import bisect
import statistics
from functools import lru_cache
from collections import Counter
from datetime import datetime, timezone

import genres


SCHEMA = """
CREATE TABLE IF NOT EXISTS station_stats (
    station           TEXT PRIMARY KEY,
    computed_at       TEXT NOT NULL,
    polled            INTEGER NOT NULL,  -- rows logged for this station
    identified        INTEGER NOT NULL,  -- matched = 1
    id_rate           REAL,              -- identified / polled * 100
    categorized       INTEGER NOT NULL,  -- matched rows resolving to >=1 category
    avg_year          INTEGER,           -- arithmetic mean release year
    median_year       INTEGER,           -- drives the era chart
    year_stdev        REAL,
    year_lo           INTEGER,           -- median - 1 SD
    year_hi           INTEGER,           -- median + 1 SD
    n_year            INTEGER,
    -- popularity among tracks last.fm knows about
    avg_playcount     INTEGER,           -- arithmetic mean, for display
    gmean_known       INTEGER,           -- geometric mean, found tracks only
    n_known           INTEGER,
    n_missing         INTEGER,           -- identified rows last.fm had no entry for
    n_zero            INTEGER,           -- found but never scrobbled
    coverage_pct      REAL,              -- n_known / identified * 100
    -- popularity counting absence as obscurity
    effective_plays   INTEGER,           -- geometric mean with NULLs imputed
    obscurity         INTEGER,           -- 0 = most played, 100 = most obscure
    obscurity_lo      INTEGER,           -- whisker: +1 SD of plays
    obscurity_hi      INTEGER,           -- whisker: -1 SD of plays
    obscurity_known   INTEGER,           -- same rank ignoring missing rows
    top_artist        TEXT,
    top_artist_n      INTEGER,
    top_category      TEXT,
    top_category_n    INTEGER,
    most_popular      TEXT,
    least_popular     TEXT
);

CREATE TABLE IF NOT EXISTS station_genres (
    station   TEXT NOT NULL,
    category  TEXT NOT NULL,
    n         INTEGER NOT NULL,   -- categorized plays hitting this category
    pct       REAL NOT NULL,      -- n / station's total category hits * 100
    PRIMARY KEY (station, category)
);

CREATE INDEX IF NOT EXISTS idx_station_genres_cat ON station_genres(category);

CREATE TABLE IF NOT EXISTS uncategorized_tags (
    tag  TEXT PRIMARY KEY,
    n    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_uncat_n ON uncategorized_tags(n DESC);
"""

# Imputed playcount for a track last.fm has no entry for. 0 places it just below
# a track with a single scrobble, which is about right: absent from the database
# is marginally more obscure than present-but-unplayed. Raise it if your NULLs
# turn out to be mostly failed lookups rather than genuinely unknown records.
MISSING_PLAYCOUNT = 0

# A station needs this many rows before its genre mix or its rank means anything.
MIN_CATEGORIZED = 5


def parse_year(acr_release, mb_year):
    """ACR release_date wins, MusicBrainz year is the fallback."""
    if acr_release and len(acr_release) >= 4 and acr_release[:4].isdigit():
        return int(acr_release[:4])
    if mb_year:
        try:
            return int(str(mb_year)[:4])
        except (ValueError, TypeError):
            return None
    return None


@lru_cache(maxsize=None)
def _unresolved(acr_genres, lf_tags):
    """Distinct tag pairs are a small fraction of total rows; memoize."""
    return tuple(genres.unresolved_tags_for_row(acr_genres, lf_tags))


def _percentile(ranked, val):
    """
    Interpolated percentile rank of val in sorted list `ranked`.
    0.0-1.0 where 1.0 = largest. None if there's nothing to rank against.
    """
    n = len(ranked)
    if val is None or n == 0:
        return None
    if n == 1:
        return 0.5
    i = bisect.bisect_left(ranked, val)
    if i <= 0:
        frac = 0.0
    elif i >= n:
        frac = float(n - 1)
    else:
        lo, hi = ranked[i - 1], ranked[i]
        frac = (i - 1) + ((val - lo) / (hi - lo) if hi > lo else 0)
    return frac / (n - 1)


def _obsc(ranked, val):
    """Percentile rank inverted into an obscurity score. 0 = most played."""
    p = _percentile(ranked, val)
    return round(100 * (1 - p)) if p is not None else None


def _gather(conn):
    """One pass over plays. Returns (by_station, uncategorized Counter)."""
    rows = conn.execute(
        "SELECT station, artist, title, matched, category, categories,"
        "       acr_genres, lf_tags, acr_release, mb_year, lf_playcount"
        "  FROM plays"
    ).fetchall()

    misses = Counter()
    by_station = {}
    for (station, artist, title, matched, category, categories,
         acr_genres, lf_tags, acr_release, mb_year, plays) in rows:
        b = by_station.setdefault(station, {
            "polled": 0, "identified": 0, "categorized": 0,
            "years": [], "known": [], "missing": 0, "zero": 0,
            "artists": Counter(), "cats": Counter(), "cat_hits": 0,
            "most": None, "least": None,
        })
        b["polled"] += 1
        if not matched:
            continue
        b["identified"] += 1
        if artist:
            b["artists"][artist] += 1

        if not category:
            misses.update(_unresolved(acr_genres, lf_tags))

        y = parse_year(acr_release, mb_year)
        if y:
            b["years"].append(y)

        # NULL and 0 mean different things here; keep them apart.
        if plays is None:
            b["missing"] += 1
        else:
            b["known"].append(plays)
            if plays == 0:
                b["zero"] += 1
            if plays > 0:
                label = f"{artist or '?'} — {title or '?'}"
                if b["most"] is None or plays > b["most"][0]:
                    b["most"] = (plays, label)
                if b["least"] is None or plays < b["least"][0]:
                    b["least"] = (plays, label)

        if categories:
            hit = False
            for c in categories.split(";"):
                c = c.strip()
                if c:
                    b["cats"][c] += 1
                    b["cat_hits"] += 1
                    hit = True
            if hit:
                b["categorized"] += 1

    return by_station, misses


def recompute(conn, this_year=None, min_tag_count=1):
    """
    Rebuild all three rollup tables from scratch.
    Returns {"stations": n, "genre_rows": n, "tags": n} for logging.
    """
    conn.executescript(SCHEMA)
    if this_year is None:
        this_year = datetime.now(timezone.utc).year
    now = datetime.now(timezone.utc).isoformat()

    by_station, misses = _gather(conn)

    # Pass 1: per-station aggregates.
    stats = {}
    for station, b in by_station.items():
        # Future years are bad ACR/MB data, not catalogue.
        years = [y for y in b["years"] if y <= this_year]
        known, missing = b["known"], b["missing"]

        median_year = round(statistics.median(years)) if years else None
        year_sd = round(statistics.stdev(years), 1) if len(years) > 1 else None

        # Depth among tracks last.fm actually has.
        pos = [p for p in known if p > 0]
        gmean_known = 10 ** statistics.mean([math.log10(p) for p in pos]) if pos else None

        # Depth counting absence. The +1 keeps zeros and imputed NULLs in range.
        scored = [math.log10(p + 1) for p in known]
        scored += [math.log10(MISSING_PLAYCOUNT + 1)] * missing
        if scored:
            lm = statistics.mean(scored)
            lsd = statistics.stdev(scored) if len(scored) > 1 else 0.0
            effective = 10 ** lm - 1
            eff_lo = 10 ** (lm - lsd) - 1   # fewer plays -> more obscure
            eff_hi = 10 ** (lm + lsd) - 1
        else:
            effective = eff_lo = eff_hi = None

        top_artist = b["artists"].most_common(1)
        top_cat = b["cats"].most_common(1)

        stats[station] = {
            "polled": b["polled"],
            "identified": b["identified"],
            "id_rate": (b["identified"] / b["polled"] * 100) if b["polled"] else 0.0,
            "categorized": b["categorized"],
            "avg_year": round(statistics.mean(years)) if years else None,
            "median_year": median_year,
            "year_stdev": year_sd,
            "year_lo": round(median_year - year_sd) if (median_year and year_sd) else median_year,
            "year_hi": round(median_year + year_sd) if (median_year and year_sd) else median_year,
            "n_year": len(years),
            "avg_playcount": round(statistics.mean(known)) if known else None,
            "gmean_known": round(gmean_known) if gmean_known else None,
            "n_known": len(known),
            "n_missing": missing,
            "n_zero": b["zero"],
            "coverage_pct": (round(100 * len(known) / b["identified"], 1)
                             if b["identified"] else None),
            "effective_plays": round(effective) if effective is not None else None,
            "most_popular": b["most"][1] if b["most"] else None,
            "least_popular": b["least"][1] if b["least"] else None,
            "top_artist": top_artist[0][0] if top_artist else None,
            "top_artist_n": top_artist[0][1] if top_artist else None,
            "top_category": top_cat[0][0] if top_cat else None,
            "top_category_n": top_cat[0][1] if top_cat else None,
            "_eff": effective, "_eff_lo": eff_lo, "_eff_hi": eff_hi,
            "_gmean": gmean_known,
            "_cats": b["cats"], "_cat_hits": b["cat_hits"],
        }

    # Pass 2: cross-station percentile ranks. Only stations with enough
    # identified plays define the scale, so one station with three logs can't
    # anchor either end of it.
    eligible = [s for s in stats.values() if s["identified"] >= MIN_CATEGORIZED]
    ranked_eff = sorted(s["_eff"] for s in eligible if s["_eff"] is not None)
    ranked_known = sorted(s["_gmean"] for s in eligible if s["_gmean"] is not None)

    for s in stats.values():
        s["obscurity"] = _obsc(ranked_eff, s["_eff"])
        # whisker endpoints swap: more plays -> lower obscurity number
        s["obscurity_lo"] = _obsc(ranked_eff, s["_eff_hi"])
        s["obscurity_hi"] = _obsc(ranked_eff, s["_eff_lo"])
        s["obscurity_known"] = _obsc(ranked_known, s["_gmean"])

    axis = set(genres.all_categories())
    genre_rows = []
    for station, s in stats.items():
        hits = s["_cat_hits"]
        if not hits:
            continue
        for cat, n in s["_cats"].items():
            if cat in axis:
                genre_rows.append((station, cat, n, round(100 * n / hits, 1)))

    tag_rows = [(t, n) for t, n in misses.items() if n >= min_tag_count]

    # Rebuild wholesale so stations and tags that vanished don't linger.
    with conn:
        conn.execute("DELETE FROM station_stats")
        conn.execute("DELETE FROM station_genres")
        conn.execute("DELETE FROM uncategorized_tags")
        conn.executemany(
            "INSERT INTO station_stats (station, computed_at, polled, identified,"
            " id_rate, categorized, avg_year, median_year, year_stdev, year_lo,"
            " year_hi, n_year, avg_playcount, gmean_known, n_known, n_missing,"
            " n_zero, coverage_pct, effective_plays, obscurity, obscurity_lo,"
            " obscurity_hi, obscurity_known, top_artist, top_artist_n,"
            " top_category, top_category_n, most_popular, least_popular)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                (station, now, s["polled"], s["identified"], round(s["id_rate"], 1),
                 s["categorized"], s["avg_year"], s["median_year"], s["year_stdev"],
                 s["year_lo"], s["year_hi"], s["n_year"], s["avg_playcount"],
                 s["gmean_known"], s["n_known"], s["n_missing"], s["n_zero"],
                 s["coverage_pct"], s["effective_plays"], s["obscurity"],
                 s["obscurity_lo"], s["obscurity_hi"], s["obscurity_known"],
                 s["top_artist"], s["top_artist_n"], s["top_category"],
                 s["top_category_n"], s["most_popular"], s["least_popular"])
                for station, s in stats.items()
            ],
        )
        conn.executemany(
            "INSERT INTO station_genres (station, category, n, pct) VALUES (?,?,?,?)",
            genre_rows,
        )
        conn.executemany(
            "INSERT INTO uncategorized_tags (tag, n) VALUES (?,?)", tag_rows
        )

    return {"stations": len(stats), "genre_rows": len(genre_rows),
            "tags": len(tag_rows)}


# ---------------------------------------------------------------------------
# Read helpers. All of these hit only the rollup tables.
# ---------------------------------------------------------------------------

def _genre_pct(conn):
    pct = {}
    for station, category, p in conn.execute(
        "SELECT station, category, pct FROM station_genres"
    ):
        pct.setdefault(station, {})[category] = p
    return pct


def dna_payload(conn):
    """The radar + spectrum data the DNA panel needs."""
    axis = genres.all_categories()
    pct = _genre_pct(conn)

    radar, totals, spectra = {}, {}, {}
    for row in conn.execute(
        "SELECT station, categorized, median_year, year_stdev, year_lo, year_hi,"
        "       n_year, obscurity, obscurity_lo, obscurity_hi, n_known, n_missing"
        "  FROM station_stats"
    ):
        (station, categorized, median_year, year_sd, year_lo, year_hi,
         n_year, obsc, obsc_lo, obsc_hi, n_known, n_missing) = row
        if not categorized:
            continue
        got = pct.get(station, {})
        radar[station] = [got.get(c, 0.0) for c in axis]
        totals[station] = categorized
        spectra[station] = {
            "year_mean": median_year, "year_sd": year_sd,
            "year_lo": year_lo, "year_hi": year_hi, "n_year": n_year,
            "obsc_mean": obsc, "obsc_lo": obsc_lo, "obsc_hi": obsc_hi,
            "n_plays": n_known, "n_missing": n_missing,
        }
    return {"categories": axis, "radar": radar,
            "totals": totals, "spectra": spectra}


def station_table(conn, min_categorized=MIN_CATEGORIZED):
    """
    One dict per station with a `genres` dict of category -> pct, ready to
    render. Needs conn.row_factory = sqlite3.Row.
    """
    axis = genres.all_categories()
    pct = _genre_pct(conn)

    out = []
    for row in conn.execute(
        "SELECT * FROM station_stats WHERE categorized >= ? ORDER BY polled DESC",
        (min_categorized,),
    ):
        if not hasattr(row, "keys"):
            raise RuntimeError("set conn.row_factory = sqlite3.Row before calling")
        d = dict(row)
        got = pct.get(d["station"], {})
        d["genres"] = {c: got.get(c, 0.0) for c in axis}
        out.append(d)
    return out


def uncategorized(conn, min_n=1, limit=None):
    sql = ("SELECT tag, n FROM uncategorized_tags WHERE n >= ?"
           " ORDER BY n DESC, tag ASC")
    params = [min_n]
    if limit:
        sql += " LIMIT ?"
        params.append(limit)
    return conn.execute(sql, params).fetchall()


def genre_leaders(conn, category, limit=10):
    """Stations playing the most of one category, by share."""
    return conn.execute(
        "SELECT g.station, g.pct, g.n, s.polled"
        "  FROM station_genres g JOIN station_stats s ON s.station = g.station"
        " WHERE g.category = ? AND s.categorized >= ?"
        " ORDER BY g.pct DESC LIMIT ?",
        (category, MIN_CATEGORIZED, limit),
    ).fetchall()


def version(conn):
    """Cheap cache key for the web app: changes whenever recompute() runs."""
    row = conn.execute(
        "SELECT MAX(computed_at), COUNT(*) FROM station_stats"
    ).fetchone()
    return tuple(row) if row else (None, 0)