import re

GENRE_ORDER = [
    'Electronic',         
    'Club / Dance',
    'Techno',
    'House',
    'Drum & Bass',
    'Hip-Hop',
    'Soul / Funk / Disco',
    'Pop',
    'Rock',
    'Punk / Metal',
    'Alternative',
    'Folk',
    'World',
    'Reggae / Dub',
    'Jazz',
    'Classical',
    'Soundtrack / Score',
    'Experimental',
    'Downtempo',
    'Ambient',
]

# Emitted only when no other electronic-family spoke matched.
RESIDUAL = 'Electronic'
ELECTRONIC_FAMILY = {'Club / Dance', 'Techno', 'House', 'Drum & Bass', 'Downtempo'}


GENRE_MAP = {
    # Electronic
    'Electronic': 'Electronic',
    'electronic': 'Electronic',
    'Electronic: Electro': 'Electronic',
    'electronic: others...': 'Electronic',
    'Elektro': 'Electronic',
    'idm': 'Downtempo',

    # Club / Dance
    'Dance': 'Club / Dance',
    'Dance & Electronic (Dance/Techno/Disco)': 'Club / Dance',
    'dance - electro': 'Club / Dance',
    'Dance | Electro': 'Club / Dance',
    'Dance/Electronic': 'Club / Dance',
    'Electro': 'Club / Dance',
    'Electronic/Dance': 'Club / Dance',
    'electronic: dance': 'Club / Dance',
    'electronica/dance': 'Club / Dance',
    'electro|dance': 'Club / Dance',
    'glitch hop': 'Club / Dance',
    'Indie Dance': 'Club / Dance',
    'progressive trance': 'Club / Dance',
    'psytrance': 'Club / Dance',
    'trance': 'Club / Dance',
    'uplifting trance': 'Club / Dance',

    # Techno
    'Dance - Techno': 'Techno',
    'electronic - techno': 'Techno',
    'Electronic: Techno': 'Techno',
    'Techno': 'Techno',
    'Techno/Electronica': 'Techno',
    'Techno/House': 'Techno',

    # House
    'afro house': 'House',
    'amapiano': 'House',
    'dance - afro house': 'House',
    'Dance - Bass House': 'House',
    'Dance - Deep House': 'House',
    'Dance - House': 'House',
    'Dance - House - Dub': 'House',
    'Electronic - Electro House': 'House',
    'gqom': 'House',
    'House': 'House',
    'house - afro': 'House',
    'house - deep': 'House',
    'house - disco': 'House',
    'house - soulful': 'House',

    # Drum & Bass
    'bass': 'Drum & Bass',
    'breaks': 'Drum & Bass',
    'Breaks & Beats': 'Drum & Bass',
    'Breaks & Beats - Electro': 'Drum & Bass',
    'dance - breaks': 'Drum & Bass',
    'Dance - Drum & Bass': 'Drum & Bass',
    'dance - drum & bass / jungle': 'Drum & Bass',
    'Dance - Garage / Bassline / Grime': 'Drum & Bass',
    'Drum & Bass': 'Drum & Bass',
    'Drum & Bass - Experimental': 'Drum & Bass',
    'Drum & Bass - Jungle': 'Drum & Bass',
    'Drum & Bass / Jungle': 'Drum & Bass',
    'Dubstep': 'Drum & Bass',
    'Dubstep & Grime': 'Drum & Bass',
    'Electronic: Drum & Bass': 'Drum & Bass',
    'Electronic: Jungle': 'Drum & Bass',
    'footwork': 'Drum & Bass',
    'Garage': 'Drum & Bass',
    'juke': 'Drum & Bass',
    'jungle': 'Drum & Bass',
    'ragga jungle': 'Drum & Bass',
    'Ram Drum & Bass': 'Drum & Bass',

    # Hip-Hop
    'chopped and screwed': 'Hip-Hop',
    'deconstructed trap': 'Hip-Hop',
    'Dirty South': 'Hip-Hop',
    'experimental hip hop': 'Hip-Hop',
    'Hip Hop': 'Hip-Hop',
    'Hip Hop / Rap': 'Hip-Hop',
    'Hip Hop/Rap': 'Hip-Hop',
    'Hip Hop/Rap - French Hip Hop': 'Hip-Hop',
    'hip hop/rap - uk hip hop': 'Hip-Hop',
    'hip hop: rap / hip hop': 'Hip-Hop',
    'Hip-Hop/Rap': 'Hip-Hop',
    'Hip-hop/Rap': 'Hip-Hop',
    'Rap': 'Hip-Hop',
    'Rap/Hip Hop': 'Hip-Hop',
    'Rap/Hip-Hop': 'Hip-Hop',
    'Urban': 'Hip-Hop',
    'Grime': 'Drum & Bass',

    # Soul / Funk / Disco
    'christian': 'Soul / Funk / Disco',
    'contemporary': 'Soul / Funk / Disco',
    'Contemporary R&B': 'Soul / Funk / Disco',
    'Contemporary Soul': 'Soul / Funk / Disco',
    'dance - nu disco / disco': 'Soul / Funk / Disco',
    'Disco': 'Soul / Funk / Disco',
    'Funk': 'Soul / Funk / Disco',
    'funk / soul': 'Soul / Funk / Disco',
    'gospel': 'Soul / Funk / Disco',
    'R & B': 'Soul / Funk / Disco',
    'R&B': 'Soul / Funk / Disco',
    'R&B/Soul': 'Soul / Funk / Disco',
    'R&B/Soul - Contemporary': 'Soul / Funk / Disco',
    'r&b/soul - disco': 'Soul / Funk / Disco',
    'R&B/Soul - Funk & Soul': 'Soul / Funk / Disco',
    'R&B/Soul/Funk': 'Soul / Funk / Disco',
    'Soul': 'Soul / Funk / Disco',
    'Soul & Funk': 'Soul / Funk / Disco',
    'soul / funk: soul': 'Soul / Funk / Disco',

    # Pop
    'adult contemporary': 'Pop',
    'french pop': 'Pop',
    'french pop: french pop': 'Pop',
    'Holiday': 'Pop',
    'j-pop': 'Pop',
    'k-pop': 'Pop',
    'new wave': 'Pop',
    'Pop': 'Pop',
    'POP': 'Pop',
    'Pop - Italo': 'Pop',
    'Pop - R&B': 'Pop',
    'Pop - Rock': 'Pop',
    'Pop Rock': 'Pop',
    'pop/rock italiano': 'Pop',
    'synthpop': 'Pop',
    'variã©tã© franã§aise': 'Pop',
    'variété française': 'Pop',
    'Vocal': 'Pop',

    # Rock
    'classic rock': 'Rock',
    'garage rock': 'Rock',
    'Hard Rock': 'Rock',
    'pop - rock: rock': 'Rock',
    'post-rock': 'Rock',
    'progressive rock': 'Rock',
    'Psychedelic': 'Rock',
    'psychedelic rock': 'Rock',
    'Rock': 'Rock',
    'Rock - Progressive': 'Rock',
    'Rock - Psychedelic': 'Rock',
    'stoner': 'Rock',
    'stoner rock': 'Rock',

    # Punk / Metal
    'Alternative/Punk': 'Punk / Metal',
    'atmospheric black metal': 'Punk / Metal',
    'black metal': 'Punk / Metal',
    'brutal death metal': 'Punk / Metal',
    'death metal': 'Punk / Metal',
    'doom': 'Punk / Metal',
    'doom metal': 'Punk / Metal',
    'emo': 'Punk / Metal',
    'funeral doom metal': 'Punk / Metal',
    'grindcore': 'Punk / Metal',
    'hardcore': 'Punk / Metal',
    'hardcore punk': 'Punk / Metal',
    'heavy metal': 'Punk / Metal',
    'Industrial/Noise': 'Punk / Metal',
    'Metal': 'Punk / Metal',
    'Metal - Hard Rock': 'Punk / Metal',
    'Metal/Hard Rock': 'Punk / Metal',
    'Metal/HardRock': 'Punk / Metal',
    'metalcore': 'Punk / Metal',
    'Metalli': 'Punk / Metal',
    'post-metal': 'Punk / Metal',
    'post-punk': 'Punk / Metal',
    'power metal': 'Punk / Metal',
    'Punk': 'Punk / Metal',
    'sludge': 'Punk / Metal',
    'stoner metal': 'Punk / Metal',
    'thrash metal': 'Punk / Metal',

    # Alternative
    'Alternative': 'Alternative',
    'alternative': 'Alternative',
    'Alternative - Indie Pop': 'Alternative',
    'alternative - indie rock': 'Alternative',
    'Alternative Rock': 'Alternative',
    'Alternative/Indie': 'Alternative',
    'alternative/indie italiana': 'Alternative',
    'Alternative|Electro': 'Alternative',
    'Alternative|Indie Pop|Indie Rock|Pop': 'Alternative',
    'Electro Pop/Electro Rock': 'Alternative',
    'Indie': 'Alternative',
    'Indie Pop': 'Alternative',
    'Indie Pop/Folk': 'Alternative',
    'Indie Rock': 'Alternative',
    'Indie Rock/Rock pop': 'Alternative',
    'pop - alternative': 'Alternative',
    'Pop - Rock: Alternative - Indie': 'Alternative',
    'Pop IndÃ©': 'Alternative',
    'Rock indÃ©': 'Alternative',
    'Vaihtoehtoinen': 'Alternative',

    # Folk
    'blues': 'Folk',
    'classic blues': 'Folk',
    'Country': 'Folk',
    'delta blues': 'Folk',
    'Folk': 'Folk',
    'Singer & Songwriter': 'Folk',
    'Singer / Songwriter': 'Folk',
    'Singer-Songwriter': 'Folk',
    'Singer-Songwriter / Folk : Contemporary Folk': 'Folk',
    'Singer/Songwriter': 'Folk',

    # World
    'Africa': 'World',
    'African': 'World',
    'african - afrobeat': 'World',
    'African Music': 'World',
    'Afrikkalainen musiikki': 'World',
    'Afro-Beat': 'World',
    'afrobeats': 'World',
    'Alternativo & Rock Latino': 'World',
    'arabic': 'World',
    'arabic pop': 'World',
    'Asian Music': 'World',
    'Bachata': 'World',
    'bossa nova': 'World',
    'Brasilianische Musik': 'World',
    'Brazil': 'World',
    'Brazilian': 'World',
    'brazilian - mpb': 'World',
    'brazilian music': 'World',
    'japanese': 'World',
    'Latin': 'World',
    'Latin / Tropical': 'World',
    'Latin Music': 'World',
    'Latin Musik': 'World',
    'latin pop': 'World',
    'Latin Urban': 'World',
    'Latinalainen musiikki': 'World',
    'Latino': 'World',
    'mpb': 'World',
    'Musique africaine': 'World',
    'Musique arabe': 'World',
    'Musique asiatique': 'World',
    'Musique brÃ©silienne': 'World',
    'RaÃ\xadces': 'World',
    'South America': 'World',
    'World': 'World',
    'World Music': 'World',
    'World Music / Regional Folklore': 'World',
    'World Music / Regional Folklore - Ethnic': 'World',
    'World Music/Ethno': 'World',
    'world music: africa': 'World',
    'world music: maghreb': 'World',
    'world music: world - fusion - others...': 'World',

    # Reggae / Dub
    'Central America/Carribean': 'Reggae / Dub',
    'Dancehall': 'Reggae / Dub',
    'Dancehall/Ragga': 'Reggae / Dub',
    'Dub': 'Reggae / Dub',
    'Reggae': 'Reggae / Dub',
    'REGGAE/SKA': 'Reggae / Dub',
    'Reggae/Ska': 'Reggae / Dub',
    'Reggae: Reggae': 'Reggae / Dub',

    # Jazz
    'Instrumental jazz': 'Jazz',
    'Jazz': 'Jazz',
    'jazz - classic': 'Jazz',
    'jazz - contemporary': 'Jazz',
    'jazz - fusion': 'Jazz',
    'jazz - jazz funk': 'Jazz',
    'jazz - nu jazz / acid jazz': 'Jazz',
    'Jazz - World': 'Jazz',
    'jazz: contemporary jazz': 'Jazz',
    'Jazz: Electro Jazz': 'Jazz',
    'Jazz: Free Jazz': 'Jazz',

    # Classical
    'Church Organ': 'Classical',
    'Classical': 'Classical',
    'Classical - Baroque': 'Classical',
    'classical crossover': 'Classical',
    'Classique': 'Classical',
    'contemporary classical': 'Classical',
    'Neo-Classical': 'Classical',

    # Soundtrack / Score
    'Anime': 'Soundtrack / Score',
    'Film Scores': 'Soundtrack / Score',
    'Films/Games': 'Soundtrack / Score',
    'films/jeux vidã©o': 'Soundtrack / Score',
    'films/jeux vidéo': 'Soundtrack / Score',
    'game': 'Soundtrack / Score',
    'musiques de films': 'Soundtrack / Score',
    'Score/Romance': 'Soundtrack / Score',
    'soundtrack': 'Soundtrack / Score',
    'Soundtracks': 'Soundtrack / Score',
    'SOUNDTRACKS/CAST ALBUMS': 'Soundtrack / Score',
    'soundtracks: movie soundtracks': 'Soundtrack / Score',
    'soundtracks: video games': 'Soundtrack / Score',
    'video game music': 'Soundtrack / Score',

    # Experimental
    'deconstructed club': 'Experimental',
    'Electronic - Experimental / Noise': 'Experimental',
    'Experimental': 'Experimental',
    'Experimental...': 'Experimental',
    'noise': 'Experimental',
    'sound collage': 'Experimental',
    'spoken word': 'Experimental',

    # Downtempo
    'Chill Out/Trip-Hop/Lounge': 'Downtempo',
    'dance - down beat / trip hop': 'Downtempo',
    'Easy Listening': 'Downtempo',
    'Electronic - Electronica / Downtempo': 'Downtempo',
    'Electronic/Trip Hop': 'Downtempo',
    'Electronic: Electronica': 'Downtempo',
    'Electronica': 'Downtempo',
    'electronica': 'Downtempo',
    'Leftfield & Chill Out': 'Downtempo',
    'Leftfield & Chill Out - Downtempo': 'Downtempo',
    'lo-fi': 'Downtempo',
    'Lounge': 'Downtempo',
    'slushwave': 'Downtempo',
    'vaporwave': 'Downtempo',

    # Ambient
    'Ambient': 'Ambient',
    'ambient': 'Ambient',
    'Electronic - Ambient': 'Ambient',
    'Electronic: Ambient': 'Ambient',
    'Leftfield & Chill Out - Ambient': 'Ambient',
    'New Age': 'Ambient',

}

_ALIAS = {
    # Club / Dance
    'big beat': 'Club / Dance',
    'club': 'Club / Dance',
    'edm': 'Club / Dance',
    'electroclash': 'Club / Dance',
    'eurodance': 'Club / Dance',
    'hardstyle': 'Club / Dance',
    'indie dance': 'Club / Dance',
    'italo': 'Club / Dance',
    'italo disco': 'Club / Dance',

    # Techno
    'acid': 'Techno',
    'acid techno': 'Techno',
    'detroit techno': 'Techno',
    'dub techno': 'Techno',
    'hard techno': 'Techno',
    'hypnotic': 'Techno',
    'minimal': 'Techno',
    'minimal techno': 'Techno',
    'raw techno': 'Techno',

    # House
    'acid house': 'House',
    'deep house': 'House',
    'disco house': 'House',
    'electro house': 'House',
    'garage house': 'House',
    'progressive house': 'House',
    'soulful house': 'House',
    'tech house': 'House',

    # Drum & Bass
    '2-step': 'Drum & Bass',
    'bassline': 'Drum & Bass',
    'breakbeat': 'Drum & Bass',
    'broken beat': 'Drum & Bass',
    'dnb': 'Drum & Bass',
    'drum and bass': 'Drum & Bass',
    'grime': 'Drum & Bass',
    'halftime': 'Drum & Bass',
    'liquid': 'Drum & Bass',
    'neurofunk': 'Drum & Bass',
    'uk garage': 'Drum & Bass',

    # Hip-Hop
    'abstract hip hop': 'Hip-Hop',
    'boom bap': 'Hip-Hop',
    'cloud rap': 'Hip-Hop',
    'conscious hip hop': 'Hip-Hop',
    'drill': 'Hip-Hop',
    'g-funk': 'Hip-Hop',
    'hip hop': 'Hip-Hop',
    'hip-hop': 'Hip-Hop',
    'trap': 'Hip-Hop',

    # Soul / Funk / Disco
    'boogie': 'Soul / Funk / Disco',
    'doo wop': 'Soul / Funk / Disco',
    'funk': 'Soul / Funk / Disco',
    'motown': 'Soul / Funk / Disco',
    'neo soul': 'Soul / Funk / Disco',
    'neo-soul': 'Soul / Funk / Disco',
    'northern soul': 'Soul / Funk / Disco',
    'nu disco': 'Soul / Funk / Disco',
    'r&b': 'Soul / Funk / Disco',
    "r'n'b": 'Soul / Funk / Disco',
    'rhythm and blues': 'Soul / Funk / Disco',
    'rnb': 'Soul / Funk / Disco',
    'soul': 'Soul / Funk / Disco',

    # Pop
    'art pop': 'Pop',
    'baroque pop': 'Pop',
    'chamber pop': 'Pop',
    'city pop': 'Pop',
    'dream pop': 'Pop',
    'pop rock': 'Pop',
    'power pop': 'Pop',
    'schlager': 'Pop',
    'shibuya-kei': 'Pop',
    'sophisti-pop': 'Pop',
    'synth pop': 'Pop',
    'yacht rock': 'Pop',

    # Rock
    'acid rock': 'Rock',
    'art rock': 'Rock',
    'blues rock': 'Rock',
    'hard rock': 'Rock',
    'indie rock': 'Rock',
    'jam band': 'Rock',
    'krautrock': 'Rock',
    'prog rock': 'Rock',
    'rock': 'Rock',
    'space rock': 'Rock',
    'surf rock': 'Rock',

    # Punk / Metal
    'coldwave': 'Punk / Metal',
    'darkwave': 'Punk / Metal',
    'ebm': 'Punk / Metal',
    'goth': 'Punk / Metal',
    'gothic': 'Punk / Metal',
    'industrial': 'Punk / Metal',
    'no wave': 'Punk / Metal',
    'post punk': 'Punk / Metal',
    'punk rock': 'Punk / Metal',
    'screamo': 'Punk / Metal',
    'thrash': 'Punk / Metal',

    # Alternative
    'alternative rock': 'Alternative',
    'bedroom pop': 'Alternative',
    'britpop': 'Alternative',
    'glitch pop': 'Alternative',
    'grunge': 'Alternative',
    'indie': 'Alternative',
    'indie pop': 'Alternative',
    'indietronica': 'Alternative',
    'jangle pop': 'Alternative',
    'math rock': 'Alternative',
    'post rock': 'Alternative',
    'shoegaze': 'Alternative',
    'slowcore': 'Alternative',
    'twee': 'Alternative',

    # Folk
    'acoustic': 'Folk',
    'alt-country': 'Folk',
    'americana': 'Folk',
    'bluegrass': 'Folk',
    'cantautori': 'Folk',
    'chanson': 'Folk',
    'country': 'Folk',
    'folk': 'Folk',
    'folk rock': 'Folk',
    'rockabilly': 'Folk',
    'singer-songwriter': 'Folk',
    'western': 'Folk',

    # World
    'africa': 'World',
    'african': 'World',
    'afrikanische musik': 'World',
    'afrobeat': 'World',
    'asian': 'World',
    'asiatische musik': 'World',
    'balkan': 'World',
    'caribbean': 'World',
    'carribean': 'World',
    'celtic': 'World',
    'central america': 'World',
    'cumbia': 'World',
    'ethio-jazz': 'World',
    'flamenco': 'World',
    'highlife': 'World',
    'indian': 'World',
    'juju': 'World',
    'klezmer': 'World',
    'korean': 'World',
    'latin rock': 'World',
    'merengue': 'World',
    'musica latina': 'World',
    'salsa': 'World',
    'samba': 'World',
    'soukous': 'World',
    'tango': 'World',
    'traditional': 'World',
    'tropicalia': 'World',
    'world': 'World',
    'world music': 'World',

    # Reggae / Dub
    'dancehall': 'Reggae / Dub',
    'dembow': 'Reggae / Dub',
    'dub': 'Reggae / Dub',
    'dubwise': 'Reggae / Dub',
    'lovers rock': 'Reggae / Dub',
    'reggae': 'Reggae / Dub',
    'reggaeton': 'Reggae / Dub',
    'rocksteady': 'Reggae / Dub',
    'roots': 'Reggae / Dub',
    'roots reggae': 'Reggae / Dub',
    'ska': 'Reggae / Dub',

    # Jazz
    'avant-garde jazz': 'Jazz',
    'be bop': 'Jazz',
    'bebop': 'Jazz',
    'big band': 'Jazz',
    'cool jazz': 'Jazz',
    'free improvisation': 'Jazz',
    'free jazz': 'Jazz',
    'fusion': 'Jazz',
    'hard bop': 'Jazz',
    'improvisation': 'Jazz',
    'jazz fusion': 'Jazz',
    'modal jazz': 'Jazz',
    'nu jazz': 'Jazz',
    'smooth jazz': 'Jazz',
    'spiritual jazz': 'Jazz',
    'swing': 'Jazz',

    # Classical
    'baroque': 'Classical',
    'chamber music': 'Classical',
    'choral': 'Classical',
    'classical music': 'Classical',
    'minimalism': 'Classical',
    'modern classical': 'Classical',
    'neoclassical': 'Classical',
    'opera': 'Classical',
    'orchestral': 'Classical',
    'romantic': 'Classical',

    # Soundtrack / Score
    'anime': 'Soundtrack / Score',
    'film score': 'Soundtrack / Score',
    'films': 'Soundtrack / Score',
    'games': 'Soundtrack / Score',
    'library music': 'Soundtrack / Score',
    'score': 'Soundtrack / Score',
    'soundtracks': 'Soundtrack / Score',

    # Experimental
    'abstract': 'Experimental',
    'avant-garde': 'Experimental',
    'avantgarde': 'Experimental',
    'electroacoustic': 'Experimental',
    'field recording': 'Experimental',
    'field recordings': 'Experimental',
    'glitch': 'Experimental',
    'musique concrete': 'Experimental',
    'outsider': 'Experimental',
    'sound art': 'Experimental',

    # Downtempo
    'balearic': 'Downtempo',
    'beats': 'Downtempo',
    'chill': 'Downtempo',
    'idm': 'Downtempo',
    'instrumental hip hop': 'Downtempo',
    'lofi': 'Downtempo',

    # Ambient
    'atmospheric': 'Ambient',
    'chill out': 'Ambient',
    'chillout': 'Ambient',
    'dark ambient': 'Ambient',
    'downtempo': 'Ambient',
    'drone': 'Ambient',
    'healing': 'Ambient',
    'meditation': 'Ambient',
    'new age': 'Ambient',
    'relaxation': 'Ambient',
    'soundscape': 'Ambient',
    'space music': 'Ambient',
    'trip hop': 'Ambient',
    'trip-hop': 'Ambient',

}

# Tags that describe a track but are not genres. Listing them explicitly keeps
# them out of the unresolved review pile, where they otherwise read as taxonomy
# gaps: "female vocalists" appears on 784 plays, "instrumental" on 650.
_JUNK = {
    "female vocalists", "male vocalists", "seen live", "favourites",
    "favorites", "beautiful", "chill vibes", "catchy", "cover", "instrumental",
    "acoustic guitar", "american", "british", "australian", "english", "usa",
    "amazing", "love", "sexy", "party", "summer", "classic", "oldies",
    "mellow", "spanish", "comedy", "karaoke", "deep", "dark", "happy", "sad",

    # platform / playlist / library noise
    "all", "miscellaneous", "miscellaneous: compilations", "compilations",
    "vhs", "moja muzika", "album", "try", "documentary", "livres audio",
    "single", "ep", "remix", "edit", "live", "mix", "dj mix", "compilation",
    # labels & imprints
    "nyege nyege tapes", "anjunabeats",
    # instruments and credits, not genres
    "piano", "guitar", "xylophone", "composer", "saxophone", "trumpet",
    "strings", "drum", "bass guitar", "vocal",
    # place names
    "los angeles", "london", "berlin", "detroit", "nyc",
    # country / nationality tags
    "ukraine", "ukrainian", "iceland", "icelandic", "croatia", "croatian",
    "serbia", "serbian", "slovenia", "ex-yu", "france", "french",
    "german", "germany", "sweden", "swedish", "netherlands",
    "uk", "united states", "mexico", "colombia", "uganda", "new zealand",
    "aotearoa", "korean", "japan",
}

# Case-insensitive index of every GENRE_MAP key.
_CI = {k.lower(): v for k, v in GENRE_MAP.items()}

# Inner delimiters seen in ACRCloud and Last.fm tag text. Deliberately does NOT
# include a bare hyphen, which would shred "Hip-Hop", "post-punk" and "lo-fi".
_INNER = re.compile(r"\s-\s|:\s|/|\||\s&\s")


def _is_junk(tag):
    if tag in _JUNK:
        return True
    return tag.rstrip("s").isdigit()          # "80s", "1990s"


def _lookup(text):
    t = text.strip().strip('"').lower()
    if not t or _is_junk(t):
        return None
    return _CI.get(t) or _ALIAS.get(t)


def _split(cell):
    """Comma-split, preserving each part whole."""
    if not cell or not isinstance(cell, str):
        return []
    return [p for p in (x.strip().strip('"') for x in cell.split(",")) if p]


def _atoms(part):
    """Break one comma-part on inner delimiters. 'Electronic: House' -> both."""
    return [a for a in (x.strip().strip('"') for x in _INNER.split(part)) if a]


def _collect(cell, into):
    """
    Resolve one tag cell into `into`. Whole part first so literal compound keys
    keep their precedence, then atoms, so 'Electronic: House' contributes House
    rather than stopping at Electronic.
    """
    for part in _split(cell):
        hit = _lookup(part)
        if hit:
            if hit not in into:
                into.append(hit)
            continue
        for atom in _atoms(part):
            a = _lookup(atom)
            if a and a not in into:
                into.append(a)


def resolve_categories(acr_genres, lf_tags=None, artist_tags=None):
    """
    Categories for one play, in source-precedence order.

    All three sources are consulted rather than falling back only when the
    previous one is empty: ACRCloud's genre field is coarse ("Dance",
    "Electronic") and was previously shadowing much better Last.fm tags on the
    plays that carry both. artist_tags is the Last.fm artist-level fallback and
    is what rescues plays whose only track tag is the word "electronic".
    """
    cats = []
    _collect(acr_genres, cats)
    _collect(lf_tags, cats)

    specific = [c for c in cats if c != RESIDUAL]
    if not specific or not (set(specific) & ELECTRONIC_FAMILY):
        # Nothing electronic-and-specific yet, so the artist tags may still help.
        _collect(artist_tags, cats)
        specific = [c for c in cats if c != RESIDUAL]

    # The residual only survives if no electronic-family spoke was found.
    if RESIDUAL in cats and (set(specific) & ELECTRONIC_FAMILY):
        cats = specific
    return cats


CATEGORY_SEP = ";"


def resolve_row(acr_genres, lf_tags=None, artist_tags=None):
    cats = resolve_categories(acr_genres, lf_tags, artist_tags)
    if not cats:
        return None, None
    return cats[0], CATEGORY_SEP.join(cats)


def all_categories():
    produced = set(GENRE_MAP.values()) | set(_ALIAS.values())
    missing = produced - set(GENRE_ORDER)
    if missing:
        raise ValueError(f"GENRE_ORDER missing categories: {sorted(missing)}")
    return list(GENRE_ORDER)


def categorize(genre, default=None):
    return GENRE_MAP.get(genre, default)


def unresolved_tags_for_row(acr_genres, lf_tags=None, artist_tags=None):
    """
    Atoms that matched nothing and are not known non-genre noise. Feeds the
    uncategorized_tags review table.
    """
    out = []
    for cell in (acr_genres, lf_tags, artist_tags):
        for part in _split(cell):
            if _lookup(part):
                continue
            for atom in _atoms(part):
                t = atom.strip().strip('"').lower()
                if not t or _is_junk(t) or _lookup(atom):
                    continue
                if t not in out:
                    out.append(t)
    return out


def add_categories(df, acr_col="acr_genres", lf_col="lf_tags"):
    """
    Add `categories`, `category` and `categories_str` columns to a copy of df.
    Explode on `categories` for per-genre counting.
    """
    out = df.copy()
    lf = out[lf_col] if lf_col in out.columns else [None] * len(out)
    out["categories"] = [resolve_categories(a, l) for a, l in zip(out[acr_col], lf)]
    out["category"] = [c[0] if c else None for c in out["categories"]]
    out["categories_str"] = [
        CATEGORY_SEP.join(c) if c else None for c in out["categories"]
    ]
    return out


def unmapped_tags(df, acr_col="acr_genres", lf_col="lf_tags", top=None):
    from collections import Counter
    miss = Counter()
    cols = [acr_col] + ([lf_col] if lf_col in df.columns else [])
    for col in cols:
        for cell in df[col].dropna():
            miss.update(unresolved_tags_for_row(cell))
    return miss.most_common(top) if top else miss