import re
import json
import sqlite3
import statistics
from pathlib import Path
from collections import Counter
from flask import Flask, render_template_string

import genres

DB_PATH = Path("/var/www/internet-radio-protocol/plays.db")
app = Flask(__name__)

PAGE = """
<!doctype html><meta charset="utf-8">
<title>One Radio [DNA]</title>
<head>
<meta name="viewport" content="width=device-width, initial-scale=0.66">
</head>
<style>
@font-face{font-family:"Archivo Light";src:url("https://one.radio/assets/Archivo-Light.ttf") format("truetype");}
@font-face{font-family:"Archivo Bold";src:url("https://one.radio/assets/Archivo-Bold.ttf") format("truetype");}
  body{
  letter-spacing: -0.05em;
  font:14px/1.4 "Archivo Light",system-ui,sans-serif;margin:2rem;color:#111}
  h1{
        border-bottom: 1px solid black;
        margin-left: 0px;
        letter-spacing: -0.05em;
        padding-bottom: 15px;
        font-family: "Archivo Bold";
        font-size: 34pt;
        color: black;
  }
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

  .scroll{max-height:500px;overflow-y:auto;border:1px solid black}

  .dna {
    padding: 0px 7px;
    border: 1px solid black;
    background-color: yellow;
    font-family: "Archivo Light";
    /* -webkit-text-stroke: 0px !important; */
    color: black;
  }

  #radar-chart {
    background-color: rgb(243,243,243);
    display: block;
    box-sizing: border-box;
    height: 560px;
    width: 560px;
    border: 1px solid black;
  }

  #plays-chart, #year-chart {
      border: 1px solid black;
      background-color: rgb(243,243,243);
  }

  #chart-div {
    display:block;
  }

  @media (orientation: landscape)  {
    #chart-div {
        display:flex;
    }
    #spectra-div {
        margin-left: 30px;
    }
  }
</style>

<h1>ONE RADIO <span class="dna">DNA</span></h1>

<h2>Station</h2>
<div style="margin:.5rem 0 1rem">
  <select id="radar-station" style="font:inherit;padding:4px 8px"></select>
  <span id="radar-n" style="margin-left:.75rem;color:#888"></span>
</div>

<div id="chart-div">

    <div>
        <h2>Most Similar Genre Makeup</h2>
        <div id="radar-similar" style="margin:.5rem 0 1rem;display:flex;gap:.5rem;flex-wrap:wrap"></div>
        <div style="max-width:560px;">
        <canvas id="radar-chart" role="img" aria-label="Radar chart of category frequency for the selected station"></canvas>
        </div>
    </div>

    <div id="spectra-div">
        <h2>Era <small>(release year, mean ±1 SD)</small></h2>
        <div style="max-width:560px;">
        <canvas id="year-chart" role="img" aria-label="Average release year with spread for the selected station"></canvas>
        </div>

        <h2>Obscurity <small>(0 = most played, 100 = most obscure, vs all stations)</small></h2>
        <div style="max-width:560px;">
        <canvas id="plays-chart" role="img" aria-label="Average last.fm playcount with spread for the selected station"></canvas>
        </div>
    </div>
</div>

<h2>Summary <small>({{summaries|length}} stations)</small></h2>
<div class="scroll">
<table class="summary sortable">
  <thead>
  <tr>
    <th>station</th><th class=num data-type=num>polled</th><th class=num data-type=num>id'd</th><th class=num data-type=num>id rate</th>
    <th>top artist</th><th class=num data-type=num>avg yr</th><th class=num data-type=num>yr stdev</th>
    <th>top category</th><th class=num data-type=num>avg plays</th><th class=txt>most popular</th><th class=txt>least popular</th>
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
    <td>{{ s.top_category }}{% if s.top_category_n %} ({{ s.top_category_n }}){% endif %}</td>
    <td class=num>{{ '{:,}'.format(s.avg_plays) if s.avg_plays else '—' }}</td>
    <td class=txt>{{ s.most_popular }}</td>
    <td class=txt>{{ s.least_popular }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>

<h2>Polls <small>({{rows|length}})</small></h2>
<div class="scroll">
<table class="plays sortable">
  <thead>
  <tr>
    <th class=c-time>time (UTC)</th><th class=c-station>station</th><th class=c-source>source</th>
    <th class=c-artist>artist</th><th class=c-title>title</th><th class=c-label>label</th>
    <th class=c-genre>genre</th><th class="c-year num" data-type=num>year</th><th class="c-plays num" data-type=num>last.fm plays</th>
    <th class=c-genre>category</th>
    <th class=c-genre>categories</th>
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
    <td>{{ r['category'] or '' }}</td>
    <td>{{ r['categories'] or '' }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>

<h2>Uncategorized tags <small>({{misses|length}} distinct, from unresolved rows only)</small></h2>
<div class="scroll">
<table class="summary sortable">
  <thead>
  <tr><th>tag</th><th class=num data-type=num>count</th></tr>
  </thead>
  <tbody>
  {% for tag, n in misses %}
  <tr>
    <td>{{ tag }}</td>
    <td class=num>{{ n }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
</div>

<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.js"></script>

<script>

  var SPECTRA = {{ spectra|tojson }};

  // Minimal horizontal error-bar plugin: draws a whisker from lo->hi with a
  // center mean dot, for a single-point dataset carrying {lo, hi, mean}.
  var whiskerPlugin = {
    id: "whisker",
    afterDatasetsDraw: function(chart){
      var meta = chart.getDatasetMeta(0);
      var pt = meta.data && meta.data[0];
      if (!pt) return;
      var list = chart.$whiskers || [];
      var xs = chart.scales.x;
      var ctx = chart.ctx;
      list.forEach(function(w, i){
        if (w.lo == null) return;
        // stack overlays on slightly different y offsets so they don't overprint
        var yc = pt.y + i * 16;
        var xlo = xs.getPixelForValue(w.lo);
        var xhi = xs.getPixelForValue(w.hi);
        var xm  = xs.getPixelForValue(w.mean);
        ctx.save();
        ctx.strokeStyle = w.color || "#000"; ctx.lineWidth = 0.5;
        ctx.beginPath(); ctx.moveTo(xlo, yc); ctx.lineTo(xhi, yc); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(xlo, yc-8); ctx.lineTo(xlo, yc+8); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(xhi, yc-8); ctx.lineTo(xhi, yc+8); ctx.stroke();
        ctx.fillStyle = w.fill || "#FFFF00"; ctx.strokeStyle = w.color || "#000";
        ctx.beginPath(); ctx.arc(xm, yc, 6, 0, 2*Math.PI); ctx.fill(); ctx.stroke();
        if (w.label != null){
          ctx.fillStyle = w.color || "#000";
          ctx.font = "12px 'Archivo Light', sans-serif";
          ctx.textAlign = "center"; ctx.textBaseline = "top";
          ctx.fillText(w.label, xm, yc + 12);
        }
        ctx.restore();
      });
    }
  };

  function makeSpectrum(canvasId, opts){
    return new Chart(document.getElementById(canvasId), {
      type: "scatter",
      data: { datasets: [{ data: [{x: 0, y: 0}], pointRadius: 0 }] },
      options: {
        responsive: true,
        scales: {
          x: Object.assign({ position: "bottom" }, opts.x),
          y: { display: false, min: -1, max: 1 }
        },
        plugins: { legend: { display: false }, tooltip: { enabled: false } }
      },
      plugins: [whiskerPlugin]
    });
  }

var YEAR_MIN = {{ year_min|tojson }};
var YEAR_MAX = new Date().getFullYear();
var yearChart = makeSpectrum("year-chart", {
    x: {
      type: "linear", min: YEAR_MIN, max: YEAR_MAX,
      ticks: { callback: function(v){ return String(v); } }
    }
  });  var playsChart = makeSpectrum("plays-chart", {
    x: { type: "linear", min: 0, max: 100 }
  });

 function spectrumWhiskers(station){
    // returns {year:[...], plays:[...]} base whisker arrays for a station
    var s = SPECTRA[station] || {};
    var year = (s.year_mean != null)
      ? [{ lo: s.year_lo, hi: s.year_hi, mean: s.year_mean,
           label: String(s.year_mean), color: "#000", fill: "#FFFF00" }]
      : [];
    var plays = (s.obsc_mean != null)
      ? [{ lo: s.obsc_lo, hi: s.obsc_hi, mean: s.obsc_mean,
           label: s.obsc_mean + " / 100", color: "#000", fill: "#FFFF00" }]
      : [];
    return { year: year, plays: plays };
  }

  function updateSpectra(station){
    var w = spectrumWhiskers(station);
    yearChart.$whiskers = w.year;
    yearChart.data.datasets[0].data = w.year.length ? [{x: w.year[0].mean, y: 0}] : [];
    yearChart.update();
    playsChart.$whiskers = w.plays;
    playsChart.data.datasets[0].data = w.plays.length ? [{x: w.plays[0].mean, y: 0}] : [];
    playsChart.update();
  }

  function addSpectrumOverlay(station, color){
    var s = SPECTRA[station] || {};
    if (s.year_mean != null){
      yearChart.$whiskers.push({ station: station, lo: s.year_lo, hi: s.year_hi,
        mean: s.year_mean, label: String(s.year_mean), color: color, fill: color });
      yearChart.update();
    }
    if (s.obsc_mean != null){
       playsChart.$whiskers.push({ station: station, lo: s.obsc_lo, hi: s.obsc_hi,
        mean: s.obsc_mean, label: s.obsc_mean + " / 100", color: color, fill: color });
      playsChart.update();
    }
  }

  function removeSpectrumOverlay(station){
    function drop(chart){
      chart.$whiskers = chart.$whiskers.filter(function(w){ return w.station !== station; });
      chart.update();
    }
    drop(yearChart); drop(playsChart);
  }

  var RADAR_AXIS = {{ radar_axis|tojson }};
  var RADAR_DATA = {{ radar_data|tojson }};
  var RADAR_TOTALS = {{ radar_totals|tojson }};

  var OVERLAY_COLORS = ["#00acff", "#ff0000", "#00ffa4"];

  (function(){
    var sel = document.getElementById("radar-station");
    var nLabel = document.getElementById("radar-n");
    var simBox = document.getElementById("radar-similar");

    var eligible = Object.keys(RADAR_DATA)
      .filter(function(s){ return (RADAR_TOTALS[s] || 0) >= 5; });

    eligible.forEach(function(s){
      var o = document.createElement("option");
      o.value = s; o.textContent = s + " (" + RADAR_TOTALS[s] + ")";
      sel.appendChild(o);
    });

    function dist(a, b){
      var s = 0;
      for (var i = 0; i < a.length; i++){ var d = a[i] - b[i]; s += d * d; }
      return Math.sqrt(s);
    }

    // The 3 eligible stations whose proportion vectors are nearest `station`.
    var MAX_DIST = 100 * Math.SQRT2;   // ~141.4, two disjoint proportion vectors

    function nearest(station){
      var base = RADAR_DATA[station] || [];
      return eligible
        .filter(function(s){ return s !== station; })
        .map(function(s){
          var d = dist(base, RADAR_DATA[s]);
          return { s: s, d: d, sim: Math.round(100 * (1 - d / MAX_DIST)) };
        })
        .sort(function(a, b){ return a.d - b.d; })
        .slice(0, 3);
    }

    function setN(s){
      nLabel.textContent = "n = " + (RADAR_TOTALS[s] || 0).toLocaleString();
    }

    function baseDataset(station){
      return {
        label: station,
        data: RADAR_DATA[station] || [],
        backgroundColor: "rgba(255,255,0,1)",
        borderColor: "#000000",
        borderWidth: 1,
        pointBackgroundColor: "#000000",
        pointRadius: 1,
        order: 2   // draw the main (filled yellow) polygon behind overlays
      };
    }
    function rgba(hex, a){
        var n = parseInt(hex.slice(1), 16);
        return "rgba(" + (n >> 16 & 255) + "," + (n >> 8 & 255) + "," + (n & 255) + "," + a + ")";
        }

    function overlayDataset(station, color){
      return {
        label: station,
        data: RADAR_DATA[station] || [],
        backgroundColor: rgba(color, 0.3),
        borderColor: color,
        borderWidth: 1,
        pointBackgroundColor: color,
        pointRadius: 1,
        order: 1
      };
    }

    var chart = new Chart(document.getElementById("radar-chart"), {
      type: "radar",
      data: { labels: RADAR_AXIS, datasets: [baseDataset(eligible[0] || "")] },
      options: {
        responsive: true,
        scales: { r: {
          beginAtZero: true,
          ticks: { display: false },
          grid: { display: false },
          pointLabels: { font: { size: 11 } }
        }},
        plugins: { legend: { display: false } }
      }
    });

    // Rebuild the similar-station buttons for the current selection.
    function renderSimilar(station){
      simBox.innerHTML = "";
      nearest(station).forEach(function(item, i){
        var other = item.s;
        var color = OVERLAY_COLORS[i];
        var btn = document.createElement("button");
        btn.textContent = other + " (" + item.sim + "%, n=" + RADAR_TOTALS[other] + ")";
        btn.dataset.station = other;
        btn.dataset.color = color;
        btn.dataset.on = "0";
        btn.style.cssText =
          "font:inherit;padding:4px 10px;cursor:pointer;border:1px solid" + color + ";" +
          "background:#fff;border-top:6px solid " + color + ";";
        btn.addEventListener("click", function(){
          var on = btn.dataset.on === "1";
          if (on){
            chart.data.datasets = chart.data.datasets.filter(function(d){
              return !(d.order === 1 && d.label === other);
            });
            removeSpectrumOverlay(other);        
            btn.dataset.on = "0";
            btn.style.background = "#fff";
            btn.style.color = "#000";
          } else {
            chart.data.datasets.push(overlayDataset(other, color));
            addSpectrumOverlay(other, color);      
            btn.dataset.on = "1";
            btn.style.background = color;
            btn.style.color = "#fff";
          }
          chart.update();
        });
        simBox.appendChild(btn);
      });
    }

    function selectStation(station){
      chart.data.datasets = [baseDataset(station)];
      chart.update();
      setN(station);
      renderSimilar(station);
      updateSpectra(station);    
    }

    sel.addEventListener("change", function(){ selectStation(sel.value); });

    if (eligible.length){
      selectStation(eligible[0]);
    } else {
      nLabel.textContent = "no stations with enough data yet";
    }
  })();
</script>

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

def uncategorized(rows):
    """Count tags from rows that resolved to NO category"""
    misses = Counter()
    for r in rows:
        if not r["matched"] or r["category"]:
            continue  
        for tag in genres.unresolved_tags_for_row(r["acr_genres"], r["lf_tags"]):
            misses[tag] += 1
    return [(tag, n) for tag, n in misses.most_common() if n > 2]

def station_spectra(rows):
    """
    Per-station stats for the era and obscurity spectrums.
    - Era: linear mean/SD of release year, excluding future years (bad ACR/MB data).
    - Obscurity: percentile rank of the station's geometric-mean last.fm plays
      among all stations. 0 = highest avg plays (most popular), 100 = lowest
      (most obscure). Whisker maps the station's play mean ±1 SD onto the same
      rank axis, so the spread shows where its range sits relative to all stations.
    """
    import math
    from datetime import datetime, timezone
    this_year = datetime.now(timezone.utc).year

    by_station = {}
    for r in rows:
        by_station.setdefault(r["station"], []).append(r)

    # Pass 1: per-station geometric-mean plays (linear-space year stats too).
    tmp = {}
    for station, srows in by_station.items():
        years = [y for y in (parse_year(r) for r in srows) if y and y <= this_year]
        plays = [r["lf_playcount"] for r in srows
                 if r["lf_playcount"] and r["lf_playcount"] > 0]

        year_mean = round(statistics.mean(years)) if years else None
        year_sd = round(statistics.stdev(years), 1) if len(years) > 1 else None

        if plays:
            logs = [math.log10(p) for p in plays]
            lm = statistics.mean(logs)
            lsd = statistics.stdev(logs) if len(logs) > 1 else 0
            gmean = 10 ** lm
            g_lo = 10 ** (lm - lsd)
            g_hi = 10 ** (lm + lsd)
        else:
            gmean = g_lo = g_hi = None

        tmp[station] = {
            "year_mean": year_mean, "year_sd": year_sd,
            "year_lo": (year_mean - year_sd) if (year_mean and year_sd) else year_mean,
            "year_hi": this_year,
            "n_year": len(years),
            "gmean": gmean, "g_lo": g_lo, "g_hi": g_hi,
            "n_plays": len(plays),
        }

    # Pass 2: rank-map geometric means to 0-100 obscurity.
    ranked = sorted(g["gmean"] for g in tmp.values() if g["gmean"] is not None)
    n = len(ranked)

    def obscurity(val):
        """0 = most plays, 100 = fewest, by interpolated percentile rank."""
        if val is None or n == 0:
            return None
        if n == 1:
            return 50
        import bisect
        i = bisect.bisect_left(ranked, val)
        if i <= 0:
            frac = 0.0
        elif i >= n:
            frac = float(n - 1)
        else:
            lo, hi = ranked[i - 1], ranked[i]
            frac = (i - 1) + ((val - lo) / (hi - lo) if hi > lo else 0)
        pct = frac / (n - 1)          # 0 = fewest plays, 1 = most
        return round(100 * (1 - pct))  # invert -> obscurity

    out = {}
    for station, g in tmp.items():
        out[station] = {
            "year_mean": g["year_mean"], "year_sd": g["year_sd"],
            "year_lo": g["year_lo"], "year_hi": g["year_hi"],
            "n_year": g["n_year"],
            # obscurity axis (0-100). whisker endpoints swap: hi plays -> low obscurity.
            "obsc_mean": obscurity(g["gmean"]),
            "obsc_lo": obscurity(g["g_hi"]),   # more plays -> lower obscurity number
            "obsc_hi": obscurity(g["g_lo"]),   # fewer plays -> higher obscurity number
            "n_plays": g["n_plays"],
            # keep raw geomean for the label if you want to show actual plays
            "plays_gmean": round(g["gmean"]) if g["gmean"] else None,
        }
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

        categories = Counter()
        for r in srows:
            raw = r["category"] 
            categories.update(parse_genres(raw))
        top_category = categories.most_common(1)

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
            "top_category": top_category[0][0] if top_category else "—",
            "top_category_n": top_category[0][1] if top_category else None,
            "avg_plays": round(statistics.mean([p for p, _ in plays])) if plays else None,
            "most_popular": track_label(max(plays, key=lambda x: x[0])[1]) if plays else "—",
            "least_popular": track_label(min(plays, key=lambda x: x[0])[1]) if plays else "—",
        })
    return summaries

def station_categories(rows):
    axis = genres.all_categories()
    idx = {c: i for i, c in enumerate(axis)}
    counts = {}
    totals = {}
    for r in rows:
        if not r["matched"] or not r["categories"]:
            continue
        cnt = counts.setdefault(r["station"], Counter())
        totals[r["station"]] = totals.get(r["station"], 0) + 1   
        for c in r["categories"].split(";"):
            if c in idx:
                cnt[c] += 1
    data = {}
    for station, cnt in counts.items():
        hits = sum(cnt.values())
        if not hits:
            continue
        data[station] = [round(100 * cnt.get(c, 0) / hits, 1) for c in axis]
    return axis, data, totals

@app.route("/dna")
def dna():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM plays ORDER BY ts DESC").fetchall()
    conn.close()
    summaries = summarize(rows)
    misses = uncategorized(rows)
    radar_axis, radar_data, radar_totals = station_categories(rows)
    spectra = station_spectra(rows)
    year_min = min(
        (s["year_lo"] for s in spectra.values() if s["year_lo"] is not None),
        default=1950,
    )
    return render_template_string(
        PAGE, rows=rows, summaries=summaries, misses=misses,
        radar_axis=radar_axis, radar_data=radar_data, radar_totals=radar_totals,
        spectra=spectra, year_min=year_min,
    )