"""
Every prose descriptor for a station: genre mix, era, obscurity.
"""


def _band(value, bands, fallback):
    for cut, name in bands:
        if value >= cut:
            return name
    return fallback


def _join(names):
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return f"{', '.join(names[:-1])} and {names[-1]}"


# ---------------------------------------------------------------------------
# Genre mix
# ---------------------------------------------------------------------------
#
# The previous cuts (70/50/30/20/10/5) were calibrated when the median station's
# lead genre held 32.5% of its plays. Splitting Electronic and pulling Punk /
# Metal, Experimental and Downtempo out of their parents divides the same plays
# more ways; the median lead is now 16.2%, and under the old cuts 62 of 98
# stations landed in one band and got the same sentence shape.

GENRE_BANDS = (
    (60, "pinpoint"),
    (40, "strong"),
    (27, "lean"),
    (20, "slight"),
    (15, "mixed"),
    (10, "trace"),
    (0,  "negligible"),
)

GENRE_LEAD = {
    "pinpoint":   "Pinpoint focus on {}",
    "strong":     "Heavy focus on {}",
    "lean":       "Strong focus on {}",
    "slight":     "Focus on {}",
    "mixed":      "Variety, but leans toward {}",
    "trace":      "Wide genre variety, with a slight lean toward {}",
    "negligible": "Wide genre variety",
}

GENRE_CO_LEAD = dict(GENRE_LEAD, slight="A balance of {}", lean="A balance of {}")

GENRE_SUPPORT = {
    "lean":   " and, to a lesser degree, {}",
    "slight": ", balanced with {}",
    "mixed":  ", sometimes mixed with {}",
    "trace":  ", with {} here and there",
}

GENRE_TOP_N = 5
GENRE_MAX_NAMED = 2
GENRE_MIN_HITS = 30

# A second genre is a co-lead when it holds at least this share of the lead's,
# rather than when it happens to fall in the same band. Band equality breaks
# down as the bands narrow: Zabrij Radio at Rock 20.7% / Pop 19.3% is plainly a
# balance but straddles a cut, while Noods Radio at 13.3% / 10.0% sits inside
# one band and plainly is not.
CO_LEAD_RATIO = 0.80


def genre_band(pct):
    return _band(pct, GENRE_BANDS, "negligible")


def describe_genres(rows, min_hits=GENRE_MIN_HITS):
    """
    rows: iterable of (category, pct, n) for one station, any order.
    Returns a sentence, or None when there is too little behind it to say
    anything. n may be None, which skips the sample-size gate.
    """
    rows = sorted(rows, key=lambda r: -r[1])[:GENRE_TOP_N]
    if not rows:
        return None

    counts = [r[2] for r in rows if len(r) > 2 and r[2] is not None]
    if counts and sum(counts) < min_hits:
        return None

    lead_band = genre_band(rows[0][1])
    if lead_band == "negligible":
        return GENRE_LEAD["negligible"] + "."

    cutoff = rows[0][1] * CO_LEAD_RATIO
    peers = [r for r in rows[1:] if r[1] >= cutoff][:GENRE_MAX_NAMED - 1]
    leaders = [rows[0]] + peers
    rest = rows[len(leaders):]

    phrase = GENRE_CO_LEAD if peers else GENRE_LEAD
    text = phrase[lead_band].format(_join([r[0] for r in leaders]))

    if rest:
        support_band = genre_band(rest[0][1])
        if support_band in GENRE_SUPPORT:
            named = [r[0] for r in rest
                     if genre_band(r[1]) == support_band][:GENRE_MAX_NAMED]
            text += GENRE_SUPPORT[support_band].format(_join(named))

    return text + "."


# ---------------------------------------------------------------------------
# Era
# ---------------------------------------------------------------------------
#
# The era CENTRE barely discriminates: half the network's median year sits
# inside the four years 2016-2020. The era SPAN does, running from 2.1 to 21.7
# years of standard deviation, so the span clause carries the sentence.
#
# That span is almost entirely a BACKWARD reach. 97 of 98 stations have a mean
# release year earlier than their median, by 4 years at the median station, so
# a big year_stdev means old records pulling down, never future ones pulling up.
# The support phrases say "back" as a statement of fact.

ERA_BANDS = (
    (2023, "brandnew"),
    (2021, "current"),
    (2018, "recent"),
    (2013, "tens"),
    (2006, "aughts"),
    (0,    "older"),
)

ERA_LEAD = {
    "brandnew": "Almost entirely new releases",
    "current":  "Mostly current releases",
    "recent":   "Mostly recent releases",
    "tens":     "Centered on the 2010s",
    "aughts":   "Centered on the late 2000s",
    "older":    "Rooted in older records",
}

# Standard deviation of release year, in years.
ERA_SPAN_BANDS = (
    (17, "sprawling"),
    (13, "wide"),
    (9,  "broad"),
    (5,  "narrow"),
    (0,  "tight"),
)

ERA_SPAN = {
    # The two widest bands take the real decade from year_lo rather than a stock
    # phrase: the widest stations here bottom out anywhere from 1984 to 2001, so
    # any fixed "back to the seventies" would be wrong most of the time.
    "sprawling": ", but drawing on records from {decade} onward",
    "wide":      ", but reaching back into {decade}",
    "broad":     ", with a fair reach back",
    "narrow":    "",
    "tight":     ", rarely straying",
}

# Below this many dated tracks the span is noise.
MIN_YEARS = 30


def era_band(year):
    return _band(year, ERA_BANDS, "older")


def era_span_band(sd):
    return _band(sd, ERA_SPAN_BANDS, "tight")


def describe_era(median_year, year_sd=None, n_year=None, year_lo=None,
                 min_years=MIN_YEARS):
    """One sentence on when this station's music was made."""
    if median_year is None:
        return None
    if n_year is not None and n_year < min_years:
        return None

    text = ERA_LEAD[era_band(median_year)]
    if year_sd is None:
        return text + "."

    clause = ERA_SPAN[era_span_band(year_sd)]
    if "{decade}" in clause:
        if year_lo is None:
            clause = ", but reaching a long way back"
        else:
            clause = clause.format(decade=f"the {int(year_lo) // 10 * 10}s")
    return text + clause + "."


# ---------------------------------------------------------------------------
# Obscurity
# ---------------------------------------------------------------------------
#
# Mean of the station's per-play obscurity scores, 0-100. The old 60/40 cuts put
# 78 of 98 stations in "balanced", because the mean is tightly packed: p25 45.2,
# p75 54.4.

OBSC_BANDS = (
    (60, "deep"),
    (54, "underground"),
    (46, "balanced"),
    (40, "familiar"),
    (0,  "popular"),
)

OBSC_LEAD = {
    "deep":        "Heavily underground",
    "underground": "Leans underground",
    "balanced":    "An even balance of familiar and obscure",
    "familiar":    "Leans familiar",
    "popular":     "Mostly well-known music",
}

# obsc_track_sd / 28.87, where 1.0 is as varied as the whole track pool. Most
# stations sit near 1.0 by construction, so the old 0.95/0.70 cuts called almost
# everything "wide".
OBSC_SPREAD_BANDS = (
    (1.02, "wide"),
    (0.92, "mixed"),
    (0.80, "focused"),
    (0,    "narrow"),
)

OBSC_SPREAD = {
    "wide":    ", pulled from across the whole range",
    "mixed":   ", with a mix from either side",
    "focused": "",
    "narrow":  ", and rarely strays from it",
}

# A station is genuinely split, rather than merely varied, when BOTH tails are
# occupied and the middle is hollow. Polarity alone is not enough: NTS Sheet
# Music posts 0.86 polarity but only 0.10 of it is the popular tail, so it is
# concentrated at one end, not split across two.
SPLIT_MIN_TAIL = 0.27
SPLIT_MAX_MIDDLE = 0.27
SPLIT_TEXT = "Swings between chart-familiar and deep cuts, with little in between."

# Below this many scored plays the shape is noise.
MIN_PLAYS = 40

# Above this share of imputed NULLs the shape describes Last.fm's coverage
# rather than the station's programming.
IMPUTED_WARN = 0.30


def obsc_band(mean):
    return _band(mean, OBSC_BANDS, "popular")


def obsc_spread_band(spread):
    return _band(spread, OBSC_SPREAD_BANDS, "narrow")


def describe_obscurity(mean, spread=None, share_popular=None,
                       share_middle=None, share_underground=None,
                       n_scored=None, min_plays=MIN_PLAYS):
    """One sentence on how obscure this station's music is."""
    if mean is None:
        return None
    if n_scored is not None and n_scored < min_plays:
        return None

    if None not in (share_popular, share_middle, share_underground):
        if (min(share_popular, share_underground) >= SPLIT_MIN_TAIL
                and share_middle <= SPLIT_MAX_MIDDLE):
            return SPLIT_TEXT

    text = OBSC_LEAD[obsc_band(mean)]
    if spread is not None:
        text += OBSC_SPREAD[obsc_spread_band(spread)]
    return text + "."


def coverage_warning(identified, n_missing, threshold=IMPUTED_WARN):
    """
    Imputed tracks all pile onto obscurity 100, so heavy Last.fm gaps make a
    station look deep and look split whether or not it is. Surface this next to
    any obscurity descriptor rather than hiding it: Rukh Radio reads "Heavily
    underground" off a sample where 55% of plays had no Last.fm entry at all.
    """
    if not identified:
        return None
    share = (n_missing or 0) / identified
    if share >= threshold:
        return (f"{share:.0%} of plays had no Last.fm entry and were counted "
                f"as maximally obscure")
    return None


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------

def describe_station(row, genre_rows=None):
    """
    All three for one station_stats row (sqlite3.Row or dict), plus the warning.
    genre_rows is an iterable of (category, pct, n) from station_genres; omit it
    to skip the genre sentence.

    Returns {"genres", "era", "obscurity", "warning"}, any of which may be None.
    """
    get = row.get if hasattr(row, "get") else (lambda k: row[k])
    return {
        "genres": describe_genres(genre_rows) if genre_rows else None,
        "era": describe_era(get("median_year"), get("year_stdev"),
                            get("n_year"), get("year_lo")),
        "obscurity": describe_obscurity(
            get("obsc_track_mean"), get("obsc_spread"),
            get("share_popular"), get("share_middle"),
            get("share_underground"), get("identified")),
        "warning": coverage_warning(get("identified"), get("n_missing")),
    }


def describe_frame(sgenres, station_col="station", cat_col="category",
                   pct_col="pct", n_col="n", min_hits=GENRE_MIN_HITS):
    """pandas convenience for the genre sentence. {station: sentence or None}."""
    out = {}
    cols = [cat_col, pct_col] + ([n_col] if n_col in sgenres.columns else [])
    for station, grp in sgenres.groupby(station_col, sort=False):
        rows = [(r[0], r[1], r[2] if len(r) > 2 else None)
                for r in grp[cols].itertuples(index=False, name=None)]
        out[station] = describe_genres(rows, min_hits=min_hits)
    return out