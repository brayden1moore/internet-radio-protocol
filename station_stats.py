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
    obsc_descriptor   TEXT,              -- NULL below MIN_FOR_SHAPE plays
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
    ("obsc_descriptor", "TEXT"),
]

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

# Descriptor thresholds, gathered here so they can be tuned against real
# stations without touching describe(). Anchored to what a station drawing
# evenly from the whole pool would post: spread 1.00, middle share 0.34.
LEAN_UNDERGROUND = 60.0      # obsc_track_mean at or above this leans obscure
LEAN_POPULAR = 40.0          # at or below this leans familiar
SPREAD_FOCUSED = 0.70        # below this the station stays in one lane
SPREAD_WIDE = 0.95           # at or above this it covers the network's range
# Bimodal needs a hollow middle, not merely a wide one: 0.15 sits well under the
# 0.34 a uniform station would post, so only a real gap qualifies.
BIMODAL_MIDDLE_MAX = 0.15
BIMODAL_POLARITY_MIN = 0.85

# Above this share of imputed NULLs the distribution is describing last.fm's
# coverage rather than the station's programming.
IMPUTED_WARN = 0.30

# Distinct (artist, title) pairs define the obscurity axis, so a track on heavy
# rotation counts once and cannot drag the scale toward itself. Set False to
# weight the axis by airtime instead, which lets the highest-volume stations
# define obscurity for everyone.
DEDUPE_REFERENCE = True


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


def describe(s):
    """
    One plain sentence for the station panel, or None if the sample is too small
    to say anything. Reads the mean for the lean and the spread for the variety,
    with polarity promoted over both when a station is genuinely split: a station
    that alternates chart-pop and unknowns has a middling mean it never actually
    visits, so "balanced" would be the wrong word for it.

    Accepts either a _track_shape() dict or a sqlite3.Row from station_stats.
    """
    if s is None:
        return None
    get = s.get if hasattr(s, "get") else (lambda k, d=None: s[k])

    n = get("n_scored") or get("identified") or 0
    mean, spread = get("obsc_track_mean"), get("obsc_spread")
    if n < MIN_FOR_SHAPE or mean is None or spread is None:
        return None

    if (get("obsc_polarity") >= BIMODAL_POLARITY_MIN
            and get("share_middle") <= BIMODAL_MIDDLE_MAX
            and spread >= SPREAD_WIDE):
        if mean >= LEAN_UNDERGROUND:
            return "Swings between familiar tracks and deep cuts, mostly the deep end"
        if mean <= LEAN_POPULAR:
            return "Swings between familiar tracks and deep cuts, mostly the familiar end"
        return "Swings between chart-familiar and deep cuts, with little in between"

    if mean >= LEAN_UNDERGROUND:
        lean = "underground"
    elif mean <= LEAN_POPULAR:
        lean = "popular"
    else:
        lean = "balanced"

    if spread < SPREAD_FOCUSED:
        variety = "focused"
    elif spread < SPREAD_WIDE:
        variety = "mixed"
    else:
        variety = "wide"

    return {
        ("underground", "focused"): "Heavy slant toward underground music",
        ("underground", "mixed"):   "Mostly underground, with some familiar names",
        ("underground", "wide"):    "Mix of underground and popular music with a lean toward underground",
        ("balanced", "focused"):    "Sticks to music that is neither obscure nor chart-familiar",
        ("balanced", "mixed"):      "Broad mix of popular and underground music",
        ("balanced", "wide"):       "Equal balance of popular and underground music",
        ("popular", "focused"):     "Heavy slant toward well-known music",
        ("popular", "mixed"):       "Mostly well-known, with some deeper cuts",
        ("popular", "wide"):        "Mix of underground and popular music with a lean toward popular",
    }[(lean, variety)]


def caveat(s):
    """
    Flag when the shape is an artefact of last.fm coverage rather than
    programming. Imputed tracks all pile onto 100, so a station with many of them
    looks deep and looks split whether or not it is: a pure chart-pop station
    with half its lookups failing is numerically indistinguishable from a
    genuinely bimodal one.
    """
    if s is None:
        return None
    get = s.get if hasattr(s, "get") else (lambda k, d=None: s[k])
    identified = get("identified") or get("n_scored") or 0
    missing = get("n_missing") or get("n_imputed") or 0
    if not identified:
        return None
    share = missing / identified
    if share >= IMPUTED_WARN:
        return (f"{share:.0%} of plays had no last.fm entry and were counted as "
                f"maximally obscure")
    return None


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
            b["artists"][artist] += 1

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
    """Add the distribution columns to a station_stats that predates them."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(station_stats)")}
    if not have:
        return
    with conn:
        for name, kind in MIGRATIONS:
            if name not in have:
                conn.execute(
                    f"ALTER TABLE station_stats ADD COLUMN {name} {kind}")


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

        # Depth counting absence. The +1 keeps zeros and imputed NULLs in range.
        scored = b["scores"]
        effective = 10 ** statistics.mean(scored) - 1 if scored else None

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
        stats[station]["obsc_descriptor"] = describe(shape) if shape else None

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
        "obsc_polarity", "obsc_descriptor", "top_artist", "top_artist_n",
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

def _genre_pct(conn):
    pct = {}
    for station, category, p in conn.execute(
        "SELECT station, category, pct FROM station_genres"
    ):
        pct.setdefault(station, {})[category] = p
    return pct


def dna_payload(conn):
    """
    The radar + spectrum data the DNA panel needs.

    obsc_mean stays the station-against-stations rank the scrubber already
    plots, so nothing moves. The obsc_* shape fields are the track-against-
    tracks scale: draw whiskers around obsc_track_mean, not around obsc_mean.
    """
    axis = genres.all_categories()
    pct = _genre_pct(conn)

    radar, totals, spectra = {}, {}, {}
    for row in conn.execute(
        "SELECT station, categorized, median_year, year_stdev, year_lo, year_hi,"
        "       n_year, obscurity, n_known, n_missing, identified,"
        "       obsc_track_mean, obsc_track_sd, obsc_spread, obscurity_lo,"
        "       obscurity_hi, obsc_p10, obsc_p50, obsc_p90, obsc_qskew,"
        "       share_popular, share_middle, share_underground, obsc_polarity,"
        "       obsc_descriptor"
        "  FROM station_stats"
    ):
        (station, categorized, median_year, year_sd, year_lo, year_hi,
         n_year, obsc, n_known, n_missing, identified,
         t_mean, t_sd, spread, p25, p75, p10, p50, p90, qskew,
         s_pop, s_mid, s_und, polarity, descriptor) = row
        if not categorized:
            continue
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
            "descriptor": descriptor,
            "coverage_warning": caveat(
                {"identified": identified, "n_missing": n_missing}),
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
        d["coverage_warning"] = caveat(d)
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
        "SELECT station, obsc_track_mean, obsc_spread, obsc_descriptor"
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