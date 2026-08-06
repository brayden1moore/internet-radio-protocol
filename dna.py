# dna.py
import sqlite3
import re
import statistics
from collections import Counter
from pathlib import Path
from flask import Flask, render_template_string

DB_PATH = Path("/var/www/internet-radio-protocol/plays.db")
app = Flask(__name__)

PAGE = """
<!doctype html><meta charset="utf-8">
<title>One Radio DNA</title>
<head>
<meta name="viewport" content="width=device-width, initial-scale=0.66">
</head>
<style>
  body{font:14px/1.4 system-ui,sans-serif;margin:2rem;color:#111}
  h1{font-size:1.2rem}
  h2{font-size:1rem;margin:1.5rem 0 .5rem}
  table{border-collapse:collapse;width:100%;table-layout:fixed}
  th,td{text-align:left;padding:4px 10px;border-bottom:1px solid #eee;
        overflow:hidden;text-overflow:ellipsis}
  th{position:sticky;top:0;background:#fff;border-bottom:2px solid #ccc;
     cursor:pointer;user-select:none}
  th:hover{background:#f3f3f3}
  th.sorted-asc::after{content:" \\2191";color:#888}
  th.sorted-desc::after{content:" \\2193";color:#888}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  tr:hover{background:#fafafa}
  .miss{color:#999}

  table.summary td, table.summary th{white-space:nowrap}
  table.summary td.txt{white-space:normal}

  table.plays{table-layout:fixed}
  table.plays .c-time{width:11%}
  table.plays .c-station{width:9%}
  table.plays .c-source{width:7%}
  table.plays .c-artist{width:15%}
  table.plays .c-title{width:19%}
  table.plays .c-label{width:11%}
  table.plays .c-genre{width:14%}
  table.plays .c-year{width:5%}
  table.plays .c-plays{width:9%}
  table.plays td{white-space:nowrap}
  table.plays td.wrap{white-space:normal}
</style>

<h1>One Radio DNA</h1>

<h2>Summary <small>({{summaries|length}} stations)</small></h2>
<table class="summary sortable">
  <thead>
  <tr>
    <th>station</th><th class=num data-type=num>polled</th><th class=num data-type=num>id'd</th><th class=num data-type=num>id rate</th>
    <th>top artist</th><th class=num data-type=num>avg yr</th><th class=num data-type=num>yr stdev</th>
    <th>top genre</th><th class=num data-type=num>avg plays</th><th class=txt>most popular</th><th class=txt>least popular</th>
  </tr>
  </thead>
  <tbody>
  {% for s in summaries %}
  <tr>
    <td>{{ s.station }}</td>
    <td class=num>{{ '{:,}'.format(s.total) }}</td>
    <td class=num>{{ '{:,}'.format(s.identified) }}</td>
    <td class=num>{{ '%.0f'|format(s.id_rate) }}%</td>
    <td class=txt>{{ s.top_artist }}{% if s.top_artist_n %} ({{ s.top_artist_n }}){% endif %}</td>
    <td class=num>{{ s.avg_year or '—' }}</td>
    <td class=num>{{ s.year_stdev or '—' }}</td>
    <td>{{ s.top_genre }}{% if s.top_genre_n %} ({{ s.top_genre_n }}){% endif %}</td>
    <td class=num>{{ '{:,}'.format(s.avg_plays) if s.avg_plays else '—' }}</td>
    <td class=txt>{{ s.most_popular }}</td>
    <td class=txt>{{ s.least_popular }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>

<h2>Polls <small>({{rows|length}})</small></h2>
<table class="plays sortable">
  <thead>
  <tr>
    <th class=c-time>time (UTC)</th><th class=c-station>station</th><th class=c-source>source</th>
    <th class=c-artist>artist</th><th class=c-title>title</th><th class=c-label>label</th>
    <th class=c-genre>genre</th><th class="c-year num" data-type=num>year</th><th class="c-plays num" data-type=num>last.fm plays</th>
  </tr>
  </thead>
  <tbody>
  {% for r in rows %}
  <tr class="{{ 'miss' if not r['matched'] else '' }}">
    <td class=wrap>{{ r['ts'][:19].replace('T',' ') }}</td>
    <td>{{ r['station'] }}</td>
    <td>{{ r['source'] }}</td>
    <td>{{ r['artist'] or '' }}</td>
    <td>{{ r['title'] or '' }}</td>
    <td>{{ r['acr_label'] or '' }}</td>
    <td>{{ r['acr_genres'] or r['mb_genre'] or r['lf_tags'] or '' }}</td>
    <td>{{ r['acr_release'][:4] if r['acr_release'] else (r['mb_year'] or '') }}</td>
    <td class=num>{{ '{:,}'.format(r['lf_playcount']) if r['lf_playcount'] else '' }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>

<script>
document.querySelectorAll("table.sortable").forEach(function(table){
  var ths = table.tHead.rows[0].cells;
  Array.prototype.forEach.call(ths, function(th, col){
    th.addEventListener("click", function(){
      var tbody = table.tBodies[0];
      var rows = Array.prototype.slice.call(tbody.rows);
      var numeric = th.dataset.type === "num";
      var asc = !th.classList.contains("sorted-asc");

      Array.prototype.forEach.call(ths, function(h){
        h.classList.remove("sorted-asc","sorted-desc");
      });
      th.classList.add(asc ? "sorted-asc" : "sorted-desc");

      function val(row){
        var t = row.cells[col].textContent.trim();
        if(numeric){
          var n = parseFloat(t.replace(/[^0-9.\\-]/g,""));
          return isNaN(n) ? -Infinity : n;
        }
        return t.toLowerCase();
      }

      rows.sort(function(a,b){
        var x = val(a), y = val(b);
        if(x < y) return asc ? -1 : 1;
        if(x > y) return asc ? 1 : -1;
        return 0;
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  });
});
</script>
"""


def parse_year(r):
    if r["acr_release"] and len(r["acr_release"]) >= 4 and r["acr_release"][:4].isdigit():
        return int(r["acr_release"][:4])
    if r["mb_year"]:
        try:
            return int(str(r["mb_year"])[:4])
        except (ValueError, TypeError):
            return None
    return None


def parse_genres(raw):
    """Split messy genre/tag strings into normalized tokens."""
    if not raw:
        return []
    # split on commas, semicolons, slashes, pipes
    parts = re.split(r"[,;/|]+", str(raw))
    out = []
    for p in parts:
        g = p.strip().strip("\"'[]{}").lower()
        g = re.sub(r"\s+", " ", g)
        if g and g not in ("n/a", "none", "unknown", "null"):
            out.append(g)
    return out


def summarize(rows):
    by_station = {}
    for r in rows:
        by_station.setdefault(r["station"], []).append(r)

    summaries = []
    for station, srows in sorted(by_station.items()):
        total = len(srows)
        matched = [r for r in srows if r["matched"]]
        identified = len(matched)

        artists = Counter(r["artist"] for r in srows if r["artist"])
        top_artist = artists.most_common(1)

        genres = Counter()
        for r in srows:
            raw = r["acr_genres"] or r["mb_genre"] or r["lf_tags"]
            genres.update(parse_genres(raw))
        top_genre = genres.most_common(1)

        years = [y for y in (parse_year(r) for r in srows) if y]
        plays = [(r["lf_playcount"], r) for r in srows if r["lf_playcount"]]

        def track_label(r):
            a, t = r["artist"] or "?", r["title"] or "?"
            return f"{a} — {t}"

        summaries.append({
            "station": station,
            "total": total,
            "identified": identified,
            "id_rate": (identified / total * 100) if total else 0,
            "top_artist": top_artist[0][0] if top_artist else "—",
            "top_artist_n": top_artist[0][1] if top_artist else None,
            "avg_year": round(statistics.mean(years)) if years else None,
            "year_stdev": round(statistics.stdev(years), 1) if len(years) > 1 else None,
            "top_genre": top_genre[0][0] if top_genre else "—",
            "top_genre_n": top_genre[0][1] if top_genre else None,
            "avg_plays": round(statistics.mean([p for p, _ in plays])) if plays else None,
            "most_popular": track_label(max(plays, key=lambda x: x[0])[1]) if plays else "—",
            "least_popular": track_label(min(plays, key=lambda x: x[0])[1]) if plays else "—",
        })
    return summaries


@app.route("/dna")
def dna():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM plays ORDER BY ts DESC LIMIT 500"
    ).fetchall()
    conn.close()
    summaries = summarize(rows)
    return render_template_string(PAGE, rows=rows, summaries=summaries)