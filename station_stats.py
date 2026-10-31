import math
import re
import bisect
import statistics
from functools import lru_cache
from collections import Counter
from datetime import datetime, timezone

import genres
import descriptors


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
    effective_plays   INTEGER,           -- geometric mean over all polls; unknown + unidentified = 0
    obscurity         INTEGER,           -- station rank: 0 = most played, 100 = most obscure
    obscurity_known   INTEGER,           -- same rank ignoring missing rows
    -- Shape of this station's own plays on the track obscurity axis. Every
    -- matched play is ranked against the pool of distinct tracks the network
    -- plays, so each one carries its own 0-100 score and a station has a
    -- distribution rather than a single point. See _track_shape().
    --
    -- These live on a different scale from `obscurity` above: that column ranks
    -- stations against stations, these rank tracks against tracks. Plot
    -- whiskers around obsc_track_mean, never around obscurity.
    obsc_track_mean   REAL,              -- mean of this station's per-play scores
    obsc_track_sd     REAL,
    obsc_spread       REAL,              -- sd / 28.87; 1.0 = as varied as the pool
    obscurity_lo      REAL,              -- p25 of per-play scores
    obscurity_hi      REAL,              -- p75
    obsc_p10          REAL,
    obsc_p50          REAL,
    obsc_p90          REAL,
    obsc_qskew        REAL,              -- -1..1; >0 = long tail into the underground
    share_popular     REAL,              -- plays scoring <= 33
    share_middle      REAL,
    share_underground REAL,              -- plays scoring >= 67
    obsc_polarity     REAL,              -- share_popular + share_underground
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

# CREATE TABLE IF NOT EXISTS leaves an existing station_stats alone, so the
# distribution columns have to be added by hand on an established database.
# obscurity_lo/obscurity_hi changed type and meaning: they used to be a
# track-level standard deviation pushed through the station-level ranking, which
# made their width a function of how tightly the stations clustered rather than
# of the station's own variety. They are now quartiles on the track axis.
MIGRATIONS = [
    ("obsc_track_mean", "REAL"),
    ("obsc_track_sd", "REAL"),
    ("obsc_spread", "REAL"),
    ("obsc_p10", "REAL"),
    ("obsc_p50", "REAL"),
    ("obsc_p90", "REAL"),
    ("obsc_qskew", "REAL"),
    ("share_popular", "REAL"),
    ("share_middle", "REAL"),
    ("share_underground", "REAL"),
    ("obsc_polarity", "REAL"),
]

# Columns that used to be written and are now generated on read. Dropped on
# migration so nothing downstream picks up a stale sentence: obsc_descriptor was
# stored by an earlier calibration that put 78 of 100 stations into the same two
# phrasings, and it stayed in the database long after the wording had moved on.
RETIRED = ["obsc_descriptor"]

# Imputed playcount for a track last.fm has no entry for. 0 places it just below
# a track with a single scrobble, which is about right: absent from the database
# is marginally more obscure than present-but-unplayed. Raise it if your NULLs
# turn out to be mostly failed lookups rather than genuinely unknown records.
MISSING_PLAYCOUNT = 0

# A station needs this many rows before its genre mix or its rank means anything.
MIN_CATEGORIZED = 5

# Below this many plays the *shape* of a distribution is noise, even though the
# mean is still usable. Numbers are always written; the descriptor is withheld.
MIN_FOR_SHAPE = 40

# SD of a uniform distribution over 0-100. A station drawing evenly from the
# whole pool scores this, so sd / UNIFORM_SD reads as "how much of the network's
# range does this station cover", with 1.0 meaning all of it.
UNIFORM_SD = 100 / math.sqrt(12)          # 28.87

# Tercile cuts on the 0-100 track obscurity axis.
POPULAR_BELOW = 33.0
UNDERGROUND_ABOVE = 67.0

# Distinct (artist, title) pairs define the obscurity axis, so a track on heavy
# rotation counts once and cannot drag the scale toward itself. Set False to
# weight the axis by airtime instead, which lets the highest-volume stations
# define obscurity for everyone.
DEDUPE_REFERENCE = True


# Typical lead bytes of UTF-8 that was read as Latin-1 ("é" -> "Ã©", "ö" -> "Ã¶",
# Cyrillic -> "Ð…"/"Ñ…", CJK -> "æ…"/"ç…"/"å…"/"ä…"/"è…"/"é…"/"ã…").
_MOJIBAKE_HINT = re.compile("[\u00c2-\u00c5\u00d0\u00d1\u00e2-\u00e9][\u0080-\u00bf]")


def fix_text(s):
    """
    Undo UTF-8-read-as-Latin-1 ("RollÃ©n" -> "Rollén"). Safe on clean text: only
    attempted when the telltale byte pairs are present, and only kept if the
    round trip decodes cleanly.
    """
    if not s or not isinstance(s, str) or not _MOJIBAKE_HINT.search(s):
        return s
    try:
        return s.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return s


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


# ---------------------------------------------------------------------------
# Per-track obscurity
# ---------------------------------------------------------------------------

def _play_score(playcount):
    """Playcounts are lognormal-ish; rank on the log. NULL is imputed."""
    if playcount is None:
        playcount = MISSING_PLAYCOUNT
    return math.log10(max(0, playcount) + 1)


def _track_obscurity(reference, score):
    """One play's obscurity, 0-100. 100 = nobody has heard it."""
    n = len(reference)
    if n < 2:
        return None
    lo = bisect.bisect_left(reference, score)
    hi = bisect.bisect_right(reference, score)
    # Midpoint of the tied block, so a wall of identical zeros does not all land
    # on the same extreme.
    rank = (lo + hi - 1) / 2
    return 100 * (1 - rank / (n - 1))


def _quantile(sorted_vals, q):
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return sorted_vals[0]
    pos = q * (n - 1)
    i = int(pos)
    frac = pos - i
    if i + 1 >= n:
        return sorted_vals[-1]
    return sorted_vals[i] * (1 - frac) + sorted_vals[i + 1] * frac


def _track_shape(values, n_imputed=0):
    """Distribution summary for one station's per-play obscurity scores."""
    vals = sorted(values)
    n = len(vals)
    if n == 0:
        return None

    mean = statistics.mean(vals)
    sd = statistics.stdev(vals) if n > 1 else 0.0
    p10, p25, p50, p75, p90 = (_quantile(vals, q)
                               for q in (0.10, 0.25, 0.50, 0.75, 0.90))

    # Bowley skew on the 10/50/90 points. Bounded, and unbothered by the spike
    # of imputed zeros at the top of the axis, unlike the third moment.
    span = p90 - p10
    qskew = ((p90 - p50) - (p50 - p10)) / span if span > 1e-9 else 0.0

    pop = sum(1 for v in vals if v <= POPULAR_BELOW) / n
    und = sum(1 for v in vals if v >= UNDERGROUND_ABOVE) / n

    return {
        "n_scored": n,
        "n_imputed": n_imputed,
        "imputed_share": n_imputed / n,
        "obsc_track_mean": mean,
        "obsc_track_sd": sd,
        "obsc_spread": sd / UNIFORM_SD,
        "obsc_p10": p10, "obscurity_lo": p25, "obsc_p50": p50,
        "obscurity_hi": p75, "obsc_p90": p90,
        "obsc_qskew": qskew,
        "share_popular": pop,
        "share_middle": 1 - pop - und,
        "share_underground": und,
        "obsc_polarity": pop + und,
    }



# ---------------------------------------------------------------------------
# Gather
# ---------------------------------------------------------------------------

def _gather(conn):
    """
    One pass over plays.
    Returns (by_station, uncategorized Counter, reference pool).

    The reference pool is the sorted list of distinct-track log playcounts that
    every play is later ranked against. Built here so the per-track obscurity
    costs no extra scan: the raw scores are kept per station and turned into
    ranks once the pool is complete.
    """
    rows = conn.execute(
        "SELECT station, artist, title, matched, category, categories,"
        "       acr_genres, lf_tags, acr_release, mb_year, lf_playcount"
        "  FROM plays"
    ).fetchall()

    misses = Counter()
    by_station = {}
    ref_seen = {}      # (artist, title) -> score, deduped
    ref_all = []       # untitled rows, or every row when DEDUPE_REFERENCE is off

    for (station, artist, title, matched, category, categories,
         acr_genres, lf_tags, acr_release, mb_year, plays) in rows:
        b = by_station.setdefault(station, {
            "polled": 0, "identified": 0, "categorized": 0,
            "years": [], "known": [], "missing": 0, "zero": 0,
            "scores": [],
            "artists": Counter(), "cats": Counter(), "cat_hits": 0,
            "most": None, "least": None,
        })
        b["polled"] += 1
        if not matched:
            continue
        b["identified"] += 1
        if artist:
            # credit the lead artist, so "X, Y" and "X feat. Z" both count toward X
            lead = fix_text(_primary_artist(artist))
            if lead and lead.lower() not in _NOT_AN_ARTIST:
                b["artists"][lead] += 1

        if not category:
            misses.update(_unresolved(acr_genres, lf_tags))

        y = parse_year(acr_release, mb_year)
        if y:
            b["years"].append(y)

        # Every matched play gets a score, NULLs included; that is the whole
        # point of imputing rather than dropping them.
        score = _play_score(plays)
        b["scores"].append(score)

        key = ((artist or "").strip().lower(), (title or "").strip().lower())
        if not DEDUPE_REFERENCE or key == ("", ""):
            ref_all.append(score)
        elif key not in ref_seen:
            ref_seen[key] = score

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

    reference = sorted(ref_all + list(ref_seen.values()))
    return by_station, misses, reference


def _migrate(conn):
    """Bring an existing station_stats up to the current column set."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(station_stats)")}
    if not have:
        return
    with conn:
        for name, kind in MIGRATIONS:
            if name not in have:
                conn.execute(
                    f"ALTER TABLE station_stats ADD COLUMN {name} {kind}")
        for name in RETIRED:
            if name in have:
                try:
                    conn.execute(
                        f"ALTER TABLE station_stats DROP COLUMN {name}")
                except Exception:
                    pass          # SQLite < 3.35; a stale column is harmless


def recompute(conn, this_year=None, min_tag_count=1):
    """
    Rebuild all three rollup tables from scratch.
    Returns {"stations": n, "genre_rows": n, "tags": n, "reference": n}.
    """
    conn.executescript(SCHEMA)
    _migrate(conn)
    if this_year is None:
        this_year = datetime.now(timezone.utc).year
    now = datetime.now(timezone.utc).isoformat()

    by_station, misses, reference = _gather(conn)

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

        # Depth counting absence: every poll counts, so plays Last.fm doesn't know
        # AND polls we couldn't identify at all both count as 0 plays. (Same
        # number the About page's "most obscure / most agreeable" use.) The +1
        # keeps zeros in range of the log.
        scored = b["scores"]
        effective = (10 ** (sum(scored) / b["polled"]) - 1) if scored and b["polled"] else None

        # Shape of the same plays on the track obscurity axis.
        shape = _track_shape(
            [_track_obscurity(reference, s) for s in scored], missing
        ) if scored and len(reference) >= 2 else None

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
            "_eff": effective,
            "_gmean": gmean_known,
            "_cats": b["cats"], "_cat_hits": b["cat_hits"],
            "_shape": shape,
        }

        # Flatten the shape onto the row, rounded for storage.
        for col in ("obsc_track_mean", "obsc_track_sd", "obsc_p10",
                    "obscurity_lo", "obsc_p50", "obscurity_hi", "obsc_p90"):
            stats[station][col] = round(shape[col], 1) if shape else None
        for col in ("obsc_spread", "obsc_qskew", "share_popular",
                    "share_middle", "share_underground", "obsc_polarity"):
            stats[station][col] = round(shape[col], 3) if shape else None

    # Pass 2: cross-station percentile ranks. Only stations with enough
    # identified plays define the scale, so one station with three logs can't
    # anchor either end of it.
    eligible = [s for s in stats.values() if s["identified"] >= MIN_CATEGORIZED]
    ranked_eff = sorted(s["_eff"] for s in eligible if s["_eff"] is not None)
    ranked_known = sorted(s["_gmean"] for s in eligible if s["_gmean"] is not None)

    for s in stats.values():
        s["obscurity"] = _obsc(ranked_eff, s["_eff"])
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

    columns = (
        "station", "computed_at", "polled", "identified", "id_rate",
        "categorized", "avg_year", "median_year", "year_stdev", "year_lo",
        "year_hi", "n_year", "avg_playcount", "gmean_known", "n_known",
        "n_missing", "n_zero", "coverage_pct", "effective_plays", "obscurity",
        "obscurity_known", "obsc_track_mean", "obsc_track_sd", "obsc_spread",
        "obscurity_lo", "obscurity_hi", "obsc_p10", "obsc_p50", "obsc_p90",
        "obsc_qskew", "share_popular", "share_middle", "share_underground",
        "obsc_polarity", "top_artist", "top_artist_n",
        "top_category", "top_category_n", "most_popular", "least_popular",
    )

    def row(station, s):
        s = dict(s, station=station, computed_at=now,
                 id_rate=round(s["id_rate"], 1))
        return tuple(s[c] for c in columns)

    # Rebuild wholesale so stations and tags that vanished don't linger.
    with conn:
        conn.execute("DELETE FROM station_stats")
        conn.execute("DELETE FROM station_genres")
        conn.execute("DELETE FROM uncategorized_tags")
        conn.executemany(
            f"INSERT INTO station_stats ({','.join(columns)})"
            f" VALUES ({','.join('?' * len(columns))})",
            [row(station, s) for station, s in stats.items()],
        )
        conn.executemany(
            "INSERT INTO station_genres (station, category, n, pct) VALUES (?,?,?,?)",
            genre_rows,
        )
        conn.executemany(
            "INSERT INTO uncategorized_tags (tag, n) VALUES (?,?)", tag_rows
        )

    return {"stations": len(stats), "genre_rows": len(genre_rows),
            "tags": len(tag_rows), "reference": len(reference)}


# ---------------------------------------------------------------------------
# Read helpers. All of these hit only the rollup tables.
# ---------------------------------------------------------------------------

def _genre_pct(conn, with_counts=False):
    """
    {station: {category: pct}}, or {station: [(category, pct, n)]} when
    with_counts -- the descriptor needs n to gate on sample size.
    """
    out = {}
    for station, category, p, n in conn.execute(
        "SELECT station, category, pct, n FROM station_genres"
    ):
        if with_counts:
            out.setdefault(station, []).append((category, p, n))
        else:
            out.setdefault(station, {})[category] = p
    return out


def dna_payload(conn):
    """
    The radar + spectrum data the DNA panel needs.

    obsc_mean stays the station-against-stations rank the scrubber already
    plots, so nothing moves. The obsc_* shape fields are the track-against-
    tracks scale: draw whiskers around obsc_track_mean, not around obsc_mean.

    The three prose fields are generated here rather than stored, so editing a
    phrase in descriptors.py takes effect on the next request instead of on the
    next recompute.
    """
    axis = genres.all_categories()
    pct = _genre_pct(conn)
    gsent = _genre_pct(conn, with_counts=True)

    radar, totals, spectra = {}, {}, {}
    for row in conn.execute(
        "SELECT station, categorized, median_year, year_stdev, year_lo, year_hi,"
        "       n_year, obscurity, n_known, n_missing, identified,"
        "       obsc_track_mean, obsc_track_sd, obsc_spread, obscurity_lo,"
        "       obscurity_hi, obsc_p10, obsc_p50, obsc_p90, obsc_qskew,"
        "       share_popular, share_middle, share_underground, obsc_polarity,"
        "       top_artist, top_artist_n"
        "  FROM station_stats"
    ):
        (station, categorized, median_year, year_sd, year_lo, year_hi,
         n_year, obsc, n_known, n_missing, identified,
         t_mean, t_sd, spread, p25, p75, p10, p50, p90, qskew,
         s_pop, s_mid, s_und, polarity, top_artist, top_artist_n) = row
        if not categorized:
            continue
        prose = descriptors.describe_station(
            {"median_year": median_year, "year_stdev": year_sd,
             "n_year": n_year, "year_lo": year_lo,
             "obsc_track_mean": t_mean, "obsc_spread": spread,
             "share_popular": s_pop, "share_middle": s_mid,
             "share_underground": s_und, "identified": identified,
             "n_missing": n_missing},
            gsent.get(station))
        got = pct.get(station, {})
        radar[station] = [got.get(c, 0.0) for c in axis]
        totals[station] = categorized
        spectra[station] = {
            "year_mean": median_year, "year_sd": year_sd,
            "year_lo": year_lo, "year_hi": year_hi, "n_year": n_year,
            "obsc_mean": obsc,
            "n_plays": n_known, "n_missing": n_missing,
            # track-scale distribution
            "obsc_track_mean": t_mean, "obsc_track_sd": t_sd,
            "obsc_spread": spread,
            "obsc_lo": p25, "obsc_hi": p75,
            "obsc_p10": p10, "obsc_p50": p50, "obsc_p90": p90,
            "obsc_qskew": qskew,
            "share_popular": s_pop, "share_middle": s_mid,
            "share_underground": s_und, "obsc_polarity": polarity,
            # prose
            "genre_descriptor": prose["genres"],
            "era_descriptor": prose["era"],
            "obsc_descriptor": prose["obscurity"],
            "coverage_warning": prose["warning"],
            "top_artist": top_artist, "top_artist_n": top_artist_n,
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
    gsent = _genre_pct(conn, with_counts=True)

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
        prose = descriptors.describe_station(d, gsent.get(d["station"]))
        d["genre_descriptor"] = prose["genres"]
        d["era_descriptor"] = prose["era"]
        d["obsc_descriptor"] = prose["obscurity"]
        d["coverage_warning"] = prose["warning"]
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


def obscurity_leaders(conn, kind="underground", limit=10):
    """
    Stations at one end of the track obscurity axis, or the most varied.
    kind: "underground" | "popular" | "varied" | "split".
    """
    order = {
        "underground": "obsc_track_mean DESC",
        "popular": "obsc_track_mean ASC",
        "varied": "obsc_spread DESC",
        "split": "obsc_polarity DESC, share_middle ASC",
    }[kind]
    return conn.execute(
        "SELECT station, obsc_track_mean, obsc_spread"
        "  FROM station_stats"
        " WHERE identified >= ? AND obsc_track_mean IS NOT NULL"
        f" ORDER BY {order} LIMIT ?",
        (MIN_FOR_SHAPE, limit),
    ).fetchall()


def version(conn):
    """Cheap cache key for the web app: changes whenever recompute() runs."""
    row = conn.execute(
        "SELECT MAX(computed_at), COUNT(*) FROM station_stats"
    ).fetchone()
    return tuple(row) if row else (None, 0)

# ---------------------------------------------------------------------------
# Network-wide distributions (About page)
# ---------------------------------------------------------------------------

# Last.fm playcount buckets, by order of magnitude. The per-track 0-100
# obscurity score can't be used here: it's a percentile rank against this same
# pool of songs, so across all songs it comes out flat by construction. Raw
# playcounts on a log scale show the actual shape.
PLAYCOUNT_BINS = [
    (1, 10, "1–9"),
    (10, 100, "10–99"),
    (100, 1_000, "100–999"),
    (1_000, 10_000, "1K–10K"),
    (10_000, 100_000, "10K–100K"),
    (100_000, 1_000_000, "100K–1M"),
    (1_000_000, 10_000_000, "1M–10M"),
    (10_000_000, None, "10M+"),
]


def network_payload(conn, this_year=None):
    """
    Distributions across every distinct song (artist + title) the network has
    played, so a track on heavy rotation counts once:
      genres     share of category hits per axis category (sums to ~100)
      years      {year: songs}
      playcounts last.fm playcount buckets, plus songs last.fm doesn't know
    """
    if this_year is None:
        this_year = datetime.now(timezone.utc).year
    axis = genres.all_categories()
    on_axis = set(axis)

    songs = {}   # key -> [categories, year, playcount]
    artists = set()
    stations = set()
    first_ts = None
    n_plays = 0
    for (ts, station, artist, title, categories, acr_release, mb_year, plays) in conn.execute(
        "SELECT ts, station, artist, title, categories, acr_release, mb_year, lf_playcount"
        "  FROM plays WHERE matched = 1"
    ):
        n_plays += 1
        stations.add(station)
        if ts and (first_ts is None or ts < first_ts):
            first_ts = ts
        key = ((artist or "").strip().lower(), (title or "").strip().lower())
        if key[0]:
            artists.add(key[0])
        if key == ("", ""):
            continue
        y = parse_year(acr_release, mb_year)
        if y and (y > this_year or y <= 1900):   # 1900 is a placeholder date in ACR/MB
            y = None
        s = songs.get(key)
        if s is None:
            songs[key] = [categories, y, plays, fix_text(artist.strip()) if artist else "",
                          fix_text(title.strip()) if title else "", [station]]
        else:  # fill gaps from later sightings of the same song
            if station not in s[5]: s[5].append(station)
            if not s[0] and categories: s[0] = categories
            if s[1] is None and y: s[1] = y
            if s[2] is None and plays is not None: s[2] = plays

    cat_hits = Counter()
    years = Counter()
    bins = [0] * len(PLAYCOUNT_BINS)
    n_zero = n_unknown = 0
    for categories, y, plays, *_ in songs.values():
        if categories:
            for c in categories.split(";"):
                c = c.strip()
                if c in on_axis:
                    cat_hits[c] += 1
        if y:
            years[y] += 1
        if plays is None:
            n_unknown += 1
        elif plays <= 0:
            n_zero += 1
        else:
            for i, (lo, hi, _) in enumerate(PLAYCOUNT_BINS):
                if plays >= lo and (hi is None or plays < hi):
                    bins[i] += 1
                    break

    total_hits = sum(cat_hits.values()) or 1
    year_list = sorted(years.elements())
    # songs Last.fm doesn't know count as 0 plays
    playcounts = sorted((s[2] or 0) for s in songs.values())
    median_pc = statistics.median(playcounts) if playcounts else None
    year_med = round(statistics.median(year_list)) if year_list else None

    # A few real songs that sit right at the median: released in the median
    # year, with a playcount closest (on a log scale) to the median playcount.
    examples = []
    if median_pc and year_med:
        target = math.log10(median_pc + 1)
        near = sorted(
            (abs(math.log10((s[2] or 0) + 1) - target), s[3], s[4], s[2], s[5])
            for s in songs.values()
            if s[1] == year_med and s[2] and s[3] and s[4]
        )
        examples = [{"artist": a, "title": t, "playcount": p, "stations": st}
                    for _, a, t, p, st in near[:25] if 'Wop' not in a and 'Jan & Dean' not in a]
    top = cat_hits.most_common(1)
    return {
        "n_songs": len(songs),
        "n_artists": len(artists),
        "n_stations": len(stations),
        "first_ts": first_ts,
        "median_playcount": round(median_pc) if median_pc is not None else None,
        "median_examples": examples,
        "top_genre": top[0][0] if top else None,
        "top_genre_pct": 100 * top[0][1] / total_hits if top else 0,
        "n_plays": n_plays,
        "categories": axis,
        "genres": [round(100 * cat_hits[c] / total_hits, 2) for c in axis],
        "years": {str(y): n for y, n in sorted(years.items())},
        "year_median": round(statistics.median(year_list)) if year_list else None,
        "n_year": len(year_list),
        "playcounts": (
            [{"label": "0", "n": n_zero}] +
            [{"label": lab, "n": bins[i]} for i, (_, _, lab) in enumerate(PLAYCOUNT_BINS)]
        ),
        "n_unknown": n_unknown,
    }


# ---------------------------------------------------------------------------
# Network highlights (About page): superlatives + most-played artists/songs
# ---------------------------------------------------------------------------

HIGHLIGHT_MIN_POLLS = 100        # a station needs this many polls to compete
HIGHLIGHT_MIN_IDENTIFIED = 30
# Credits that aren't really an artist "playing" on a station. Lowercase.
_NOT_AN_ARTIST = {"various artists", "various", "va", "unknown", "unknown artist", "[unknown]",
                  "anonymous", "traditional", "n/a",
                  "john richards"}   # KEXP's morning host, identified during talk breaks
_ARTIST_SPLIT = re.compile(r"\s*(?:,|&| feat\.? | ft\.? | featuring | x )\s*", re.I)


def _primary_artist(artist):
    return _ARTIST_SPLIT.split(artist.strip())[0].strip() if artist else ""


def highlights(conn, top_n=5, candidates=12):
    """
    Superlatives come back as short ranked lists (best first) so the page can
    skip stations it doesn't currently show.

    typical_plays: geometric mean of Last.fm plays over EVERY poll of a station,
    with unidentified polls and songs Last.fm doesn't know counted as 0. Lowest
    = most obscure, highest = most agreeable.

    Top artists / songs rank by how many polls caught them playing (ties broken
    by how many different stations played them). Back-to-back polls of the same
    song on the same station count once: songs are minutes long and polls are
    15+ minutes apart, so a repeat is a stuck now-playing feed, not a new airing.
    """
    per_station = {}                   # station -> [sum log(p+1), polls, identified]
    artists, songs = {}, {}            # key -> {"name"/"artist","title", "stations": set, "plays": n}
    last_song = {}                     # station -> song key of its previous poll
    for station, matched, artist, title, plays in conn.execute(
        "SELECT station, matched, artist, title, lf_playcount FROM plays ORDER BY station, ts"
    ):
        st = per_station.setdefault(station, [0.0, 0, 0])
        st[1] += 1
        p = plays if (matched and plays is not None) else 0
        st[0] += math.log10(max(0, p) + 1)
        if not matched or not artist or not title:
            continue
        st[2] += 1
        s_key = (fix_text(artist.strip()).lower(), fix_text(title.strip()).lower())
        repeat = last_song.get(station) == s_key
        last_song[station] = s_key
        if repeat:
            continue
        a_disp = fix_text(_primary_artist(artist))
        a_key = a_disp.lower()
        if a_key and a_key not in _NOT_AN_ARTIST:
            a = artists.setdefault(a_key, {"name": a_disp, "stations": set(), "plays": 0})
            a["stations"].add(station); a["plays"] += 1
        s = songs.setdefault(s_key, {"artist": fix_text(artist.strip()), "title": fix_text(title.strip()),
                                     "stations": set(), "plays": 0})
        s["stations"].add(station); s["plays"] += 1

    # Same formula as station_stats.effective_plays (all polls; unknown and
    # unidentified count as 0), kept unrounded here so near-ties rank properly.
    eligible = {k: v for k, v in per_station.items()
                if v[1] >= HIGHLIGHT_MIN_POLLS and v[2] >= HIGHLIGHT_MIN_IDENTIFIED}
    typical = sorted(((10 ** (v[0] / v[1]) - 1, k) for k, v in eligible.items()))
    obscure = [{"station": k, "typical_plays": round(t)} for t, k in typical[:candidates]]
    agreeable = [{"station": k, "typical_plays": round(t)} for t, k in reversed(typical[-candidates:])]

    # era + variety from the rollup tables
    years = conn.execute(
        "SELECT station, median_year FROM station_stats"
        " WHERE median_year IS NOT NULL AND n_year >= ? ORDER BY median_year",
        (HIGHLIGHT_MIN_IDENTIFIED,),
    ).fetchall()
    oldest = [{"station": s, "median_year": y} for s, y in years[:candidates]]
    newest = [{"station": s, "median_year": y} for s, y in reversed(years[-candidates:])]

    spread = []
    by_station = {}
    for station, pct in conn.execute(
        "SELECT g.station, g.pct FROM station_genres g JOIN station_stats s ON s.station = g.station"
        " WHERE s.categorized >= ?", (HIGHLIGHT_MIN_IDENTIFIED,)
    ):
        by_station.setdefault(station, []).append(pct)
    # Eclectic = how many genres get a real share of airtime (>= 1% of genre tags),
    # ties broken by how evenly the station spreads across them (Shannon entropy).
    n_axis = len(genres.all_categories())
    for station, pcts in by_station.items():
        tot = sum(pcts) or 1
        ent = -sum((p / tot) * math.log(p / tot) for p in pcts if p > 0)
        spread.append((len([p for p in pcts if p >= 1]), ent, station))
    spread.sort(reverse=True)
    eclectic = [{"station": s, "genres": n, "of": n_axis} for n, _, s in spread[:candidates]]

    def top(d, label):
        ranked = sorted(d.values(), key=lambda v: (-v["plays"], -len(v["stations"])))
        out = []
        for v in ranked[:top_n]:
            item = {k: v[k] for k in v if k not in ("stations",)}
            item["n_stations"] = len(v["stations"])
            out.append(item)
        return out

    return {
        "most_obscure": obscure,
        "most_agreeable": agreeable,
        "most_eclectic": eclectic,
        "oldest_ears": oldest,
        "newest_ears": newest,
        "top_artists": top(artists, "name"),
        "top_songs": top(songs, "title"),
    }


# ---------------------------------------------------------------------------
# "You Might Like" (site + app). One implementation, served by /dna/similar.
# ---------------------------------------------------------------------------

SIMILAR_WEIGHTS = {"genre": 0.6, "year": 0.2, "obsc": 0.2}
_similar_scales = {"key": None, "val": None}


def _genre_dist(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def similarity_scales(dna):
    """
    Each distance is divided by its spread across stations so genre, era and
    obscurity are comparable before weighting. Cached per payload.
    """
    key = id(dna)
    if _similar_scales["key"] == key:
        return _similar_scales["val"]
    names = [s for s in dna["radar"] if (dna["totals"].get(s) or 0) >= MIN_CATEGORIZED]
    g_max = max((_genre_dist(dna["radar"][a], dna["radar"][b])
                 for i, a in enumerate(names) for b in names[i + 1:]), default=1) or 1
    def rng(k):
        v = [dna["spectra"][s][k] for s in names if dna["spectra"].get(s, {}).get(k) is not None]
        return (max(v) - min(v)) if v else 0
    val = {"genre": g_max, "year": rng("year_mean") or 1, "obsc": rng("obsc_mean") or 1}
    _similar_scales.update(key=key, val=val)
    return val


def similar_stations(dna, station, limit=30):
    """
    Nearest stations by genre mix (60%), median release year (20%) and
    obscurity rank (20%). A station missing year/obscurity data is judged on
    what it has (weights renormalise). Returns best first:
    [{"station", "pct", "year_mean", "obsc_mean", "top_artist"}].
    Callers filter out stations they don't list (offline, hidden), so ask for
    a few more than you show.
    """
    radar, spectra, totals = dna["radar"], dna["spectra"], dna["totals"]
    base = radar.get(station)
    if not base:
        return []
    sc = similarity_scales(dna)
    me = spectra.get(station, {})
    out = []
    for name, vec in radar.items():
        if name == station or (totals.get(name) or 0) < MIN_CATEGORIZED or len(vec) != len(base):
            continue
        them = spectra.get(name, {})
        parts = [(SIMILAR_WEIGHTS["genre"], _genre_dist(base, vec) / sc["genre"])]
        if me.get("year_mean") is not None and them.get("year_mean") is not None:
            parts.append((SIMILAR_WEIGHTS["year"], abs(me["year_mean"] - them["year_mean"]) / sc["year"]))
        if me.get("obsc_mean") is not None and them.get("obsc_mean") is not None:
            parts.append((SIMILAR_WEIGHTS["obsc"], abs(me["obsc_mean"] - them["obsc_mean"]) / sc["obsc"]))
        wsum = sum(w for w, _ in parts)
        d = math.sqrt(sum(w * v * v for w, v in parts) / wsum)
        out.append((d, {
            "station": name,
            "pct": max(0, round(100 * (1 - d))),
            "year_mean": them.get("year_mean"),
            "obsc_mean": them.get("obsc_mean"),
            "top_artist": them.get("top_artist"),
        }))
    out.sort(key=lambda x: x[0])
    return [x for _, x in out[:limit]]


# ---------------------------------------------------------------------------
# Daily Set: three stations a day at different distances from one you love.
# ---------------------------------------------------------------------------

import random as _random

# Where each role is drawn from, as a slice of the anchor's similarity
# ranking (0 = closest station, 1 = furthest).
DAILY_ROLES = (
    ("close",    0.00, 0.15),
    ("sideways", 0.35, 0.60),
    ("far",      0.70, 0.90),
    ("wildcard", 0.92, 1.00),   # out of left field: the very furthest from the anchor
)
DAILY_MIN_TOTAL = 30          # a station needs this many categorized plays to be picked or to anchor


def _genre_name(cat):
    # "Club / Dance" -> "club/dance", "Hip-Hop" -> "hip-hop"
    return cat.lower().replace(" / ", "/")


def _top_genres(cats, vec, k=2, floor=6.0):
    ranked = sorted(zip(cats, vec), key=lambda cv: -cv[1])
    return [c for c, v in ranked[:k] if v >= floor]


def _daily_why(role, dna, anchor, pick):
    """One sentence on why `pick` is in today's set. Returns (text, mark):
    mark is the genre phrase inside text that the apps highlight."""
    cats = dna["categories"]
    a, p = dna["radar"][anchor], dna["radar"][pick]
    sa, sp = dna["spectra"].get(anchor, {}), dna["spectra"].get(pick, {})
    ya, yp = sa.get("year_mean"), sp.get("year_mean")
    oa, op = sa.get("obsc_mean"), sp.get("obsc_mean")
    d_year = (yp - ya) if ya is not None and yp is not None else 0
    d_obsc = (op - oa) if oa is not None and op is not None else 0
    J = descriptors._join

    if role == "close":
        shared = sorted(((min(x, y), c) for c, x, y in zip(cats, a, p) if min(x, y) >= 5),
                        reverse=True)[:2]
        mark = J([_genre_name(c) for _, c in shared]) if shared else None
        head = f"They've got similar {mark} curation as {anchor}" if mark else f"They're similar to {anchor} across the board"
        if d_obsc > 12:
            tail = " but play tracks a bit more underground."
        elif d_obsc < -12:
            tail = " but play slightly more popular tracks."
        elif d_year > 5:
            tail = f"  skewing more recent (median {round(yp)})."
        elif d_year < -5:
            tail = f" skewing older (median {round(yp)})."
        else:
            tail = "."
        return head + tail, mark

    if role == "sideways":
        more = sorted(((y - x, c) for c, x, y in zip(cats, a, p) if y - x >= 3), reverse=True)[:2]
        less = sorted(((x - y, c) for c, x, y in zip(cats, a, p) if x - y >= 3), reverse=True)[:1]
        mark = J([_genre_name(c) for _, c in more]) if more else None
        head = (f"They pull tracks from a similar depth and era as {anchor} but with a different sound" if abs(d_year) <= 6
                else f"They pull tracks from a similar depth as {anchor} but with and a different sound")
        if not mark:
            return head + ".", None
        text = f"{head}. More {mark}"
        if less:
            text += f". Less {_genre_name(less[0][1])}"
        return text + ".", mark

    if role == "wildcard":
        top = _top_genres(cats, p)
        mark = J([_genre_name(c) for c in top]) if top else None
        head = (f"Of our stations, it's least like {anchor}. Mostly {mark}" if mark
                else f"Of our stations, it's least like {anchor}")
        if abs(d_year) >= 10:
            head += f", with a median release year of {round(yp)}"
        return head + ". Give it a try.", mark

    # far
    top = _top_genres(cats, p)
    mark = J([_genre_name(c) for c in top]) if top else None
    head = f"Mostly {mark}" if mark else "A long way from what you know"
    if op is not None and op >= 80:
        tail = ", playing some of the deepest cuts of stations we track."
    elif op is not None and op <= 20:
        tail = ", playing more popular tracks on the whole."
    elif abs(d_year) >= 10:
        tail = f", with a median release of {round(yp)}."
    else:
        tail = "."
    return head + tail, mark


def daily_set(dna, date, anchor=None, exclude=(), n=6):
    """
    Today's set for one listener. `anchor` is the station they keep coming
    back to; without one (a new listener) the anchor is picked from the date,
    so everyone without history shares the same set that day.

    Returns candidates per role, best first. The same date + anchor + exclude
    always gives the same answer, so the set holds still all day. Callers skip
    candidates they can't show (offline, unlisted) and take the first left.
    """
    radar, totals = dna["radar"], dna["totals"]
    eligible = sorted(s for s in radar if (totals.get(s) or 0) >= DAILY_MIN_TOTAL)
    personal = bool(anchor and anchor in radar)
    if not personal:
        if not eligible:
            return None
        anchor = _random.Random(f"daily|{date}").choice(eligible)

    skip = set(exclude) | {anchor}
    ranked = [x for x in similar_stations(dna, anchor, limit=len(radar))
              if (totals.get(x["station"]) or 0) >= DAILY_MIN_TOTAL]
    rng = _random.Random(f"daily|{date}|{anchor}")
    used, picks = set(), {}
    for role, lo, hi in DAILY_ROLES:
        # Widen the band a step at a time if exclusions (stations they know,
        # recent picks) have emptied it, so every role still gets candidates.
        pool, pad = [], 0.0
        while not pool and pad <= 0.3:
            a = max(0.0, lo - pad); b = min(1.0, hi + pad)
            band = ranked[int(a * len(ranked)):max(int(b * len(ranked)), int(a * len(ranked)) + 1)]
            pool = [x for x in band if x["station"] not in skip and x["station"] not in used]
            pad += 0.1
        rng.shuffle(pool)
        out = []
        for x in pool[:n]:
            why, mark = _daily_why(role, dna, anchor, x["station"])
            out.append({"station": x["station"], "pct": x["pct"], "why": why, "mark": mark})
        if out:
            used.add(out[0]["station"])
        picks[role] = out
    return {"date": date, "anchor": anchor, "personal": personal,
            "roles": [r for r, _, _ in DAILY_ROLES], "picks": picks}


def daily_explain(dna, anchor, items):
    """
    Fresh wording for a set the app already holds: [(role, station)] ->
    [{"role", "station", "pct", "why", "mark"}]. The app keeps its picks for
    the whole day but re-reads the sentences, so wording edits show up
    without waiting for tomorrow's set.
    """
    if anchor not in dna["radar"]:
        return []
    pct = {x["station"]: x["pct"] for x in similar_stations(dna, anchor, limit=len(dna["radar"]))}
    out = []
    for role, station in items:
        if station not in dna["radar"] or station not in pct:
            continue
        why, mark = _daily_why(role, dna, anchor, station)
        out.append({"role": role, "station": station, "pct": pct[station], "why": why, "mark": mark})
    return out


# ---------------------------------------------------------------------------
# Daily tracks: three songs we've heard on a station, one per popularity tier.
# ---------------------------------------------------------------------------

DAILY_TRACK_TIERS = ("popular", "middle", "deep")
# How many songs each tier contributes.
DAILY_TRACK_COUNTS = {"popular": 3, "middle": 3, "deep": 2}


def _plausible_year(acr_release, mb_year):
    this_year = datetime.now(timezone.utc).year
    y = parse_year(acr_release, mb_year)
    if y is None or not (1900 <= y <= this_year + 1):
        # ACR sometimes sends placeholder dates like 2500-12-31
        y = parse_year(None, mb_year)
    return y if y is not None and 1900 <= y <= this_year + 1 else None


def daily_tracks(conn, station, date, accept=None, max_tries=8):
    """
    Songs identified on `station`, picked for `date`: DAILY_TRACK_COUNTS from
    the most popular third of its polls, the middle and the least popular
    (Last.fm playcount; unknown counts as 0). Every poll counts, so a
    song the station plays a lot is more likely to come up. Same station +
    date always gives the same three. Returns
    [{"tier", "title", "artist", "year", "category", "playcount"}].

    `accept(track)` (optional) returns the track (possibly enriched) to keep
    it, or None to skip to the tier's next candidate; at most `max_tries`
    candidates per song wanted are offered. A tier can come back short.
    """
    rows = conn.execute(
        "SELECT artist, title, category, acr_release, mb_year, lf_playcount"
        "  FROM plays"
        " WHERE station = ? AND matched = 1"
        "   AND TRIM(COALESCE(title, '')) != '' AND TRIM(COALESCE(artist, '')) != ''",
        (station,)).fetchall()
    rows = [r for r in rows if _primary_artist(fix_text(r[0])).lower() not in _NOT_AN_ARTIST]
    if not rows:
        return []
    rows.sort(key=lambda r: -(r[5] or 0))
    n = len(rows)
    tiers = (rows[:max(1, n // 3)], rows[n // 3:2 * n // 3], rows[2 * n // 3:])

    rng = _random.Random(f"tracks|{date}|{station}")
    picked, seen = [], set()
    for tier, band in zip(DAILY_TRACK_TIERS, tiers):
        band = list(band)
        rng.shuffle(band)
        want = DAILY_TRACK_COUNTS.get(tier, 1)
        got, tries = 0, 0
        for artist, title, category, acr_release, mb_year, playcount in band:
            artist, title = fix_text(artist).strip(), fix_text(title).strip()
            key = (artist.lower(), title.lower())
            if key in seen:
                continue
            seen.add(key)
            track = {
                "tier": tier,
                "title": title,
                "artist": artist,
                "year": _plausible_year(acr_release, mb_year),
                "category": category,
                "playcount": playcount,
            }
            if accept is not None:
                tries += 1
                track = accept(track)
                if track is None:
                    if tries >= max_tries * want:
                        break
                    continue
            picked.append(track)
            got += 1
            if got >= want:
                break
    return picked
