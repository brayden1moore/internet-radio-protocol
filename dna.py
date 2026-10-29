import io
import csv
import sqlite3
import colorsys
import threading
import datetime
from pathlib import Path
from flask import Flask, jsonify, request, Response

import genres
import station_stats
import match as radio_match
import time as _time

DB_PATH = Path("/var/www/internet-radio-protocol/plays.db")
app = Flask(__name__)

TABLE_COLS = ("ts, station, show, source, artist, title, acr_label, acr_genres, mb_genre, "
              "lf_tags, acr_release, mb_year, lf_playcount, matched, category, categories")

DEFAULT_ROW_LIMIT = 500

STYLE = """
<style>
@font-face{font-family:"Archivo Light";src:url("https://one.radio/assets/Archivo-Light.ttf") format("truetype");}
@font-face{font-family:"Archivo Bold";src:url("https://one.radio/assets/Archivo-Bold.ttf") format("truetype");}
@font-face{font-family:"Archivo SemiBold";src:url("https://one.radio/assets/Archivo-SemiBold.ttf") format("truetype");}
  body{
  letter-spacing: -0.05em;
  font:14px/1.4 "Archivo Light",system-ui,sans-serif;margin:0px;color:#111}
  h1{

        margin-left: 0px;
        letter-spacing: -0.05em;
        padding-bottom: 15px;
        font-family: "Archivo Bold";
        font-size: 34pt;
        color: black;
  }
  h2 {
      font-size: 1rem;
      margin: 0;
      border-bottom: 0px;
      padding: 3px 10px;
      font-family: "Archivo SemiBold";
      font-weight: normal !important;
   }
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
  .scroll-x{overflow-x:auto}

  /* The stations table is wide (one column per genre), so it scrolls
     sideways instead of being squeezed to fit. */
  table.stations{table-layout:auto;width:max-content;min-width:100%}
  table.stations th,table.stations td{white-space:nowrap}
  table.stations td.txt{max-width:220px;overflow:hidden;text-overflow:ellipsis}
  table.stations .g{border-left:1px solid rgba(0,0,0,.05);text-align:center}
  table.stations th.g{font-size:10px;letter-spacing:0;padding-top:6px}
  table.stations td.g{border-bottom:1px solid #fff}
  table.stations td.z{color:#ddd}
  table.stations .sep{border-left:1px solid #bbb}
  /* Row hover must not repaint the shaded cells, or the heat map flickers. */
  table.stations tr:hover td:not(.g){background:#fafafa}
  table.stations tr:hover{background:none}

  .dna {
    margin-left: 5px;
    padding: 4px 12px;
    background-color: yellow;
    font-family: "Archivo Light";
    color: black;
  }

  a.dl {
    float: right;
    margin: -1px 0 0 8px;
    padding: 2px 10px;
    border: 1px solid black;
    background: yellow;
    color: black;
    font-family: "Archivo Light";
    font-size: 9pt;
    text-decoration: none;
    letter-spacing: -0.03em;
  }
  a.dl:hover{background:#000;color:yellow}

  #radar-chart {
    display: block;
    box-sizing: border-box;
    height: 522px;
    width: 522px;

  }

  #plays-chart, #year-chart {
    padding: 5px;
    height: 168px !important;
    display: flex;
    align-items: center;
    justify-content: center;
    margin: auto;
  }

  #plays-chart {
    display: block;
    box-sizing: border-box;
    height: 178px;
    width: 356px;
}

  #chart-div {
    width: 560px;
    display: block;
    border: 1px solid black;
  }

  #spectra-div {
    border-left: none;
    width: 100%;
  }

  #left-div {
    border-bottom: 1px solid black;
  }

  #radar-similar {
    white-space: nowrap;
    border-bottom: 1px solid black;
    height: 86px !important;
    display: flex;
    color: black;
    gap: .5rem;
    text-wrap: var();
    flex-wrap: wrap;
    overflow: scroll;
    padding: 10px;
  }

  @media (min-width: 916px)  {
    #chart-div {
        width: fit-content;
        display:flex;
    }
    #spectra-div {
        margin-left: -1px;
        border-left: 1px solid black;
        width: 356px;
    }
    #left-div {
        width: 560px;
        border-bottom: none !important;
    }
  }
</style>"""


# embeddable core
DNA_PANEL = """
<div style="margin:.5rem 0 1rem" {{ 'hidden' if pin_station else '' }}>
  <select id="radar-station" style="font:inherit;padding:4px 8px;background-color:black;height:33px!important;outline:none!important;border-radius:0px!important;"></select>
  <span id="radar-n" style="margin-left:.75rem;color:#888"></span>
</div>

<div id="chart-div">

    <div id="left-div">
        <div style="max-width:560px;  height:551px;">
        <h2 style="margin-top: 0px;">Genre Makeup{{' (n = ' + radar_totals[pin_station]|string + ')' if pin_station else ''}}</h2>
        <canvas id="radar-chart" role="img" aria-label="Radar chart of category frequency for the selected station"></canvas>
        </div>
    </div>

    <div id="spectra-div">
        <h2 style="margin-top: 0px;">Most Similar</h2>
        <div id="radar-similar"></div>

        <h2>Era <small>(release year, median &plusmn;1 SD)</small></h2>
        <div style="max-width:560px;">
        <canvas id="year-chart" role="img" aria-label="Median release year with spread for the selected station"></canvas>
        </div>

        <h2 style="border-top:1px solid black;">Obscurity <small>(0 = most played, 100 = most obscure)</small></h2>
        <div style="max-width:560px;">
        <canvas id="plays-chart" role="img" aria-label="Relative obscurity with spread for the selected station"></canvas>
        </div>
    </div>
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
        ctx.strokeStyle = w.color || "#000"; ctx.lineWidth = 1;
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
  var YEAR_MAX = {{ year_max|tojson }};
  var yearChart = makeSpectrum("year-chart", {
    x: {
      type: "linear", min: YEAR_MIN, max: YEAR_MAX,
      ticks: { callback: function(v){ return String(v); } }
    }
  });
  var playsChart = makeSpectrum("plays-chart", {
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
           label: s.obsc_mean, color: "#000", fill: "#FFFF00" }]
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
        mean: s.obsc_mean, label: s.obsc_mean , color: color, fill: color });
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
  var PIN_STATION = {{ pin_station|tojson }};

  var OVERLAY_COLORS = ["#00acff", "#ff0000", "#00d186","#FF8F00"];

  (function(){
    var sel = document.getElementById("radar-station");
    var nLabel = document.getElementById("radar-n");
    var simBox = document.getElementById("radar-similar");

    var eligible = Object.keys(RADAR_DATA)
      .filter(function(s){ return (RADAR_TOTALS[s] || 0) >= 5; });

    if (!PIN_STATION) {
      eligible.forEach(function(s){
        var o = document.createElement("option");
        o.value = s; o.textContent = s + " (" + RADAR_TOTALS[s] + ")";
        sel.appendChild(o);
      });
    }

    function dist(a, b){
      var s = 0;
      for (var i = 0; i < a.length; i++){ var d = a[i] - b[i]; s += d * d; }
      return Math.sqrt(s);
    }

    // The 4 eligible stations whose proportion vectors are nearest `station`.
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
        .slice(0, 4);
    }

    function setN(s){
      nLabel.textContent = "n = " + (RADAR_TOTALS[s] || 0).toLocaleString();
    }

    function baseDataset(station){
      return {
        label: station,
        data: RADAR_DATA[station] || [],
        backgroundColor: "rgba(0,0,0,1)",
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
          "font:inherit;font-size:10pt;padding:4px 10px;cursor:pointer;border:1px solid" + color + ";" +
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

    var start = PIN_STATION && RADAR_DATA[PIN_STATION] ? PIN_STATION : eligible[0];
    if (start) {
      if (!PIN_STATION) sel.value = start;
      selectStation(start);
    } else {
      nLabel.textContent = "";
    }
  })();
</script>
"""

PAGE_STYLE = """
<style>
@font-face{font-family:"Archivo Light";src:url("https://one.radio/assets/Archivo-Light.ttf") format("truetype");}
@font-face{font-family:"Archivo SemiBold";src:url("https://one.radio/assets/Archivo-SemiBold.ttf") format("truetype");}
@font-face{font-family:"Archivo Bold";src:url("https://one.radio/assets/Archivo-Bold.ttf") format("truetype");}
  :root{--gray:rgb(243,243,243);--line:#e6e6e6;--yellow:#FFFF00}
  *{box-sizing:border-box}
  body{margin:0;padding:20px;color:#111;letter-spacing:-0.04em;
       font:13px/1.4 "Archivo Light",system-ui,sans-serif}
  h1{margin:0 0 24px;padding-bottom:14px;
     font:normal 34pt/1 "Archivo Bold",sans-serif;letter-spacing:-0.05em}
  .dna{margin-left:5px;padding:4px 12px;background:var(--yellow);
       font:normal 34pt/1 "Archivo Light",sans-serif}

  section{margin-bottom:36px}
  .bar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;
       border:1px solid #000;border-bottom:none;padding:6px 6px 6px 10px}
  .bar h2{margin:0;font:normal 15px/1.2 "Archivo SemiBold",sans-serif}
  .bar .meta{color:#888}
  .bar .tools{margin-left:auto;display:flex;gap:6px;align-items:center}
  .bar input[type=search]{font:inherit;letter-spacing:inherit;width:200px;padding:3px 8px;
       border:1px solid #000;border-radius:0;outline:none;background:#fff}
  .bar input[type=search]:focus{background:var(--yellow)}
  .bar .count{color:#888;font-variant-numeric:tabular-nums;white-space:nowrap}
  a.btn{padding:3px 10px;border:1px solid #000;background:var(--yellow);color:#000;
        text-decoration:none;white-space:nowrap}
  a.btn:hover{background:#000;color:var(--yellow)}
  a.btn.plain{background:#fff}
  a.btn.plain:hover{background:#000;color:#fff}

  /* platform stats */
  .stats{display:grid;grid-template-columns:repeat(4,1fr);
         border:1px solid #000;border-right:none;border-bottom:none}
  .stat{padding:12px 12px 10px;border-right:1px solid #000;border-bottom:1px solid #000}
  .stat .v{font:normal 26px/1.1 "Archivo SemiBold",sans-serif;letter-spacing:-0.05em;
           font-variant-numeric:tabular-nums}
  .stat .k{color:#888;margin-top:2px}

  /* tables */
  .scroll{max-height:520px;overflow:auto;border:1px solid #000}
  table{border-collapse:collapse;width:100%}
  th,td{text-align:left;padding:5px 10px;border-bottom:1px solid var(--line);
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:280px}
  th{position:sticky;top:0;z-index:1;background:#fff;border-bottom:1px solid #000;
     font:normal 12px/1.2 "Archivo SemiBold",sans-serif;cursor:pointer;user-select:none}
  th:hover{background:var(--gray)}
  th.sorted-asc::after{content:" \\2191"}
  th.sorted-desc::after{content:" \\2193"}
  .num{text-align:right;font-variant-numeric:tabular-nums}
  tbody tr:hover td{background:var(--gray)}
  tr.miss td{color:#aaa}
  tr[hidden]{display:none}
  .sep{border-left:1px solid #ccc}
  .empty{padding:14px 10px;color:#888;display:none}

  table.plays{table-layout:fixed;min-width:1250px}
  table.plays .c-time{width:160px}

  table.stations{width:max-content;min-width:100%}
  table.stations .g{border-left:1px solid rgba(0,0,0,.05);text-align:center;max-width:none}
  table.stations th.g{font-size:10px;letter-spacing:0;padding-top:6px}
  table.stations td.g{border-bottom:1px solid #fff}
  table.stations td.z{color:#ddd}
  /* hover must not repaint the heat-map cells */
  table.stations tbody tr:hover td.g{background:inherit}

  table.tags{max-width:600px}
  @media (max-width:700px){
    body{padding:12px}
    .bar .tools{margin-left:0;width:100%;flex-wrap:wrap}
    .bar input[type=search]{flex:1 1 140px;width:auto;min-width:0}
    .stats{grid-template-columns:repeat(2,1fr)}
  }
</style>"""


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>One Radio DNA</title>
""" + PAGE_STYLE + """
</head><body>
<h1>ONE RADIO <span class="dna">DNA</span></h1>

<section>
  <div class="bar"><h2>Platform</h2>
    {% if platform.first_ts %}<span class="meta">polling since {{ platform.first_ts[:10] }} · last poll {{ platform.last_ts[:16].replace('T',' ') }} UTC</span>{% endif %}
  </div>
  <div class="stats">
    <div class="stat"><div class="v">{{ '{:,}'.format(platform.polls) }}</div><div class="k">polls</div></div>
    <div class="stat"><div class="v">{{ '%.0f'|format(platform.id_rate) }}%</div><div class="k">identified ({{ '{:,}'.format(platform.identified) }})</div></div>
    <div class="stat"><div class="v">{{ '{:,}'.format(network.n_songs) }}</div><div class="k">distinct songs</div></div>
    <div class="stat"><div class="v">{{ '{:,}'.format(network.n_artists) }}</div><div class="k">distinct artists</div></div>
    <div class="stat"><div class="v">{{ platform.stations }}</div><div class="k">stations polled</div></div>
    <div class="stat"><div class="v">{{ network.year_median or '—' }}</div><div class="k">median release year</div></div>
    <div class="stat"><div class="v">{{ '%.0f'|format(100 * (network.n_songs - network.n_unknown) / network.n_songs) if network.n_songs else '—' }}%</div><div class="k">songs on Last.fm</div></div>
    <div class="stat"><div class="v">{{ network.top_genre or '—' }}</div><div class="k">top genre ({{ '%.0f'|format(network.top_genre_pct) }}% of tags)</div></div>
  </div>
</section>

<section>
  <div class="bar"><h2>Polls</h2>
    <span class="meta">latest {{ '{:,}'.format(rows|length) }} of {{ '{:,}'.format(total_rows) }}</span>
    <div class="tools">
      <span class="count"></span>
      <input type="search" class="filter" placeholder="Filter polls" data-table="t-plays">
      {% if rows|length < total_rows %}<a class="btn plain" href="?n={{ [rows|length * 10, 20000]|min }}">Load {{ '{:,}'.format([rows|length * 10, 20000, total_rows]|min) }}</a>{% endif %}
      <a class="btn" href="/dna/plays.csv">CSV &darr;</a>
    </div>
  </div>
  <div class="scroll">
  <table class="plays sortable" id="t-plays">
    <thead><tr>
      <th class=c-time>time (UTC)</th><th>station</th><th>show</th><th>source</th>
      <th>artist</th><th>title</th><th>label</th><th>genre</th>
      <th class=num data-type=num>year</th><th class=num data-type=num>last.fm plays</th>
      <th>category</th><th>categories</th>
    </tr></thead>
    <tbody>
    {% for r in rows %}
    <tr class="{{ 'miss' if not r['matched'] else '' }}">
      <td>{{ r['ts'][:19].replace('T',' ') }}</td>
      <td>{{ r['station'] }}</td>
      <td title="{{ r['show'] or '' }}">{{ r['show'] or '' }}</td>
      <td>{{ r['source'] or '' }}</td>
      <td title="{{ r['artist'] or '' }}">{{ r['artist'] or '' }}</td>
      <td title="{{ r['title'] or '' }}">{{ r['title'] or '' }}</td>
      <td title="{{ r['acr_label'] or '' }}">{{ r['acr_label'] or '' }}</td>
      {% set g = r['acr_genres'] or r['mb_genre'] or r['lf_tags'] or '' %}
      <td title="{{ g }}">{{ g }}</td>
      <td class=num>{{ r['acr_release'][:4] if r['acr_release'] else (r['mb_year'] or '') }}</td>
      <td class=num>{{ '{:,}'.format(r['lf_playcount']) if r['lf_playcount'] else '' }}</td>
      <td>{{ r['category'] or '' }}</td>
      <td title="{{ r['categories'] or '' }}">{{ r['categories'] or '' }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  <div class="empty">No matching rows</div>
  </div>
</section>

<section>
  <div class="bar"><h2>Stations</h2>
    <span class="meta">{{ stations|length }} · genre columns are % of that station's category hits</span>
    <div class="tools">
      <span class="count"></span>
      <input type="search" class="filter" placeholder="Filter stations" data-table="t-stations">
      <a class="btn" href="/dna/stations.csv">CSV &darr;</a>
    </div>
  </div>
  <div class="scroll">
  <table class="stations sortable" id="t-stations">
    <thead><tr>
      <th>station</th>
      <th class=num data-type=num>polled</th>
      <th class=num data-type=num>id'd</th>
      <th class=num data-type=num>id rate</th>
      <th class="num sep" data-type=num>avg yr</th>
      <th class=num data-type=num>yr sd</th>
      <th class="num sep" data-type=num>avg plays</th>
      <th class=num data-type=num>lf cover</th>
      <th class=num data-type=num>obscurity</th>
      <th class=sep>top artist</th>
      <th>top category</th>
      <th>most popular</th>
      <th>least popular</th>
      {% for c in axis %}<th class="num g{{ ' sep' if loop.first else '' }}" data-type=num
          style="border-top:5px solid {{ genre_hex[c] }}">{{ c }}</th>{% endfor %}
    </tr></thead>
    <tbody>
    {% for s in stations %}
    <tr>
      <td>{{ s.station }}</td>
      <td class=num>{{ '{:,}'.format(s.polled) }}</td>
      <td class=num>{{ '{:,}'.format(s.identified) }}</td>
      <td class=num>{{ '%.0f'|format(s.id_rate) }}%</td>
      <td class="num sep">{{ s.avg_year or '—' }}</td>
      <td class=num>{{ s.year_stdev or '—' }}</td>
      <td class="num sep">{{ '{:,}'.format(s.avg_playcount) if s.avg_playcount else '—' }}</td>
      <td class=num>{{ '%.0f'|format(s.coverage_pct) ~ '%' if s.coverage_pct is not none else '—' }}</td>
      <td class=num>{{ s.obscurity if s.obscurity is not none else '—' }}</td>
      <td class=sep>{{ s.top_artist or '—' }}{% if s.top_artist_n %} ({{ s.top_artist_n }}){% endif %}</td>
      <td>{{ s.top_category or '—' }}{% if s.top_category_n %} ({{ s.top_category_n }}){% endif %}</td>
      <td title="{{ s.most_popular or '' }}">{{ s.most_popular or '—' }}</td>
      <td title="{{ s.least_popular or '' }}">{{ s.least_popular or '—' }}</td>
      {% for c in axis %}
        {% set v = s.genres[c] %}
        <td class="num g{{ ' sep' if loop.first else '' }}{{ ' z' if not v else '' }}"
            style="{{ s.cells[c] }}">{{ '%.1f'|format(v) if v else '·' }}</td>
      {% endfor %}
    </tr>
    {% endfor %}
    </tbody>
  </table>
  <div class="empty">No matching stations</div>
  </div>
</section>

<section>
  <div class="bar"><h2>Uncategorized tags</h2>
    <span class="meta">{{ misses|length }} distinct, from unresolved rows only</span>
    <div class="tools">
      <span class="count"></span>
      <input type="search" class="filter" placeholder="Filter tags" data-table="t-tags">
      <a class="btn" href="/dna/tags.csv">CSV &darr;</a>
    </div>
  </div>
  <div class="scroll">
  <table class="tags sortable" id="t-tags">
    <thead><tr><th>tag</th><th class=num data-type=num>count</th></tr></thead>
    <tbody>
    {% for tag, n in misses %}
    <tr><td>{{ tag }}</td><td class=num>{{ n }}</td></tr>
    {% endfor %}
    </tbody>
  </table>
  <div class="empty">No matching tags</div>
  </div>
</section>

<script>
// sortable headers
document.querySelectorAll("table.sortable").forEach(function(table){
  var ths = table.tHead.rows[0].cells;
  Array.prototype.forEach.call(ths, function(th, col){
    th.addEventListener("click", function(){
      var tbody = table.tBodies[0];
      var rows = Array.prototype.slice.call(tbody.rows);
      var numeric = th.dataset.type === "num";
      var asc = !th.classList.contains("sorted-asc");
      Array.prototype.forEach.call(ths, function(h){ h.classList.remove("sorted-asc","sorted-desc"); });
      th.classList.add(asc ? "sorted-asc" : "sorted-desc");
      function val(row){
        var t = row.cells[col].textContent.trim();
        if (numeric){
          var n = parseFloat(t.replace(/[^0-9.\\-]/g,""));
          return isNaN(n) ? -Infinity : n;
        }
        return t.toLowerCase();
      }
      rows.sort(function(a,b){
        var x = val(a), y = val(b);
        return x < y ? (asc ? -1 : 1) : x > y ? (asc ? 1 : -1) : 0;
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  });
});

// filters: every word must appear somewhere in the row
document.querySelectorAll("input.filter").forEach(function(input){
  var table = document.getElementById(input.dataset.table);
  var rows = Array.prototype.slice.call(table.tBodies[0].rows);
  var text = rows.map(function(r){ return r.textContent.toLowerCase(); });
  var count = input.parentNode.querySelector(".count");
  var empty = table.parentNode.querySelector(".empty");
  var t;
  function apply(){
    var words = input.value.toLowerCase().split(/\\s+/).filter(Boolean);
    var shown = 0;
    rows.forEach(function(r, i){
      var ok = words.every(function(w){ return text[i].indexOf(w) !== -1; });
      r.hidden = !ok;
      if (ok) shown++;
    });
    count.textContent = words.length ? shown.toLocaleString() + " / " + rows.length.toLocaleString() : "";
    empty.style.display = shown ? "none" : "block";
  }
  input.addEventListener("input", function(){ clearTimeout(t); t = setTimeout(apply, 120); });
});
</script>
</body></html>
"""


EMBED = """<!doctype html><meta charset="utf-8"><title>One Radio DNA — {{ pin_station }}</title>
<head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
""" + STYLE + DNA_PANEL

# Compile once at import instead of re-parsing on every request.
PAGE_T = app.jinja_env.from_string(PAGE)
EMBED_T = app.jinja_env.from_string(EMBED)


# ---------------------------------------------------------------- db access

def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_indexes():
    """Cheap no-op after the first run; makes the LIMIT query a range scan."""
    try:
        conn = _conn()
        conn.execute("CREATE INDEX IF NOT EXISTS idx_plays_ts_desc ON plays(ts DESC)")
        # poll.py adds this too; doing it here means the page works even before
        # the first poll run with the new code
        cols = {r[1] for r in conn.execute("PRAGMA table_info(plays)")}
        if "show" not in cols:
            conn.execute("ALTER TABLE plays ADD COLUMN show TEXT")
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass  # read-only db or missing table — not fatal


def load_recent_rows(conn, limit=DEFAULT_ROW_LIMIT):
    return conn.execute(
        f"SELECT {TABLE_COLS} FROM plays ORDER BY ts DESC LIMIT ?", (limit,)
    ).fetchall()


def total_rows(conn):
    return conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]


def platform_stats(conn):
    polls, identified, first_ts, last_ts, stations = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(matched), 0), MIN(ts), MAX(ts), COUNT(DISTINCT station)"
        "  FROM plays"
    ).fetchone()
    return {
        "polls": polls, "identified": identified,
        "id_rate": 100 * identified / polls if polls else 0,
        "first_ts": first_ts, "last_ts": last_ts, "stations": stations,
    }


# ----------------------------------------------------------- genre colouring

# GENRE_ORDER is already laid out as a spectrum, so walking the hue wheel in the
# same order means neighbouring genres get neighbouring colours — the palette
# carries the same adjacency the radar axis does. Stops short of a full wrap so
# the last category doesn't collide with the first.
HUE_SPAN = 0.86
FILL_SATURATION = 0.72

# Raw HSL at a fixed lightness is perceptually lopsided: yellow-green lands
# around 5x the relative luminance of blue, so an identical share would look
# far heavier in the House column than in the Jazz one. Hue should carry the
# category and alpha should carry the magnitude — hue must not also modulate
# apparent intensity. So each hue's lightness is tuned to hit one target
# luminance, which also flattens text contrast across the row.
TARGET_LUMINANCE = 0.42

# Cell shading. Alpha is normalised against the largest share in the table
# rather than against 100, or everything would be near-invisible: a station
# spread over 20 genres rarely puts more than 40% anywhere. GAMMA < 1 lifts the
# middle of the range so small-but-real shares stay legible.
ALPHA_FLOOR = 0.08
ALPHA_CEILING = 0.85
GAMMA = 0.65


def _rel_luminance(rgb01):
    """WCAG relative luminance from 0-1 floats."""
    def ch(v):
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(v) for v in rgb01)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _at_luminance(hue, target, sat=FILL_SATURATION):
    """Bisect HSL lightness until this hue hits the target luminance."""
    lo, hi = 0.0, 1.0
    rgb = (0.0, 0.0, 0.0)
    for _ in range(24):
        mid = (lo + hi) / 2
        rgb = colorsys.hls_to_rgb(hue, mid, sat)
        if _rel_luminance(rgb) < target:
            lo = mid
        else:
            hi = mid
    return rgb


def genre_palette(axis):
    """category -> (r, g, b), a luminance-flat hue ramp following the axis order."""
    n = max(len(axis), 1)
    out = {}
    for i, c in enumerate(axis):
        rgb = _at_luminance((i / n) * HUE_SPAN, TARGET_LUMINANCE)
        out[c] = tuple(round(v * 255) for v in rgb)
    return out


def _hex(rgb):
    return "#%02x%02x%02x" % rgb


def _shade(rgb, pct, gmax):
    """Inline background for one genre cell, or '' when the share is zero."""
    if not pct:
        return ""
    t = min(pct / gmax, 1.0) ** GAMMA if gmax else 0.0
    a = ALPHA_FLOOR + (ALPHA_CEILING - ALPHA_FLOOR) * t
    return f"background:rgba({rgb[0]},{rgb[1]},{rgb[2]},{a:.3f})"


def attach_shading(stations, axis):
    """
    Precompute each station's genre cell styles. Done once per rollup rather
    than per render, and kept out of the template so Jinja stays declarative.
    """
    palette = genre_palette(axis)
    gmax = max((v for s in stations for v in s["genres"].values()), default=0.0)
    for s in stations:
        s["cells"] = {c: _shade(palette[c], s["genres"][c], gmax) for c in axis}
    return {c: _hex(palette[c]) for c in axis}, gmax


# ------------------------------------------------------------ rollup cache
# The rollups are small, but they're read on every request. Cache them against
# station_stats.version(), which changes only when the poller recomputes.

_cache = {}
_cache_lock = threading.Lock()


def rollups(conn):
    ver = station_stats.version(conn)
    with _cache_lock:
        if _cache.get("ver") == ver:
            return _cache["val"]

    payload = station_stats.dna_payload(conn)
    stations = station_stats.station_table(conn)
    genre_hex, gmax = attach_shading(stations, payload["categories"])
    val = {
        "dna": payload,
        "stations": stations,
        "genre_hex": genre_hex,
        "genre_max": gmax,
        "misses": station_stats.uncategorized(conn, min_n=3),
        "network": {**station_stats.network_payload(conn),
                    "highlights": station_stats.highlights(conn)},
    }
    with _cache_lock:
        _cache.update(ver=ver, val=val)
    return val


# ------------------------------------------------------------------ render

def render_dna(template, dna, **extra):
    spectra = dna["spectra"]
    year_min = min((s["year_lo"] for s in spectra.values() if s["year_lo"] is not None),
                   default=1950)
    year_max = max((s["year_hi"] for s in spectra.values() if s["year_hi"] is not None),
                   default=2025)
    return template.render(
        radar_axis=dna["categories"], radar_data=dna["radar"],
        radar_totals=dna["totals"], spectra=spectra,
        year_min=year_min, year_max=year_max, **extra,
    )


def csv_response(header, row_iter, filename):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(row_iter)
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# --------------------------------------------------------------------- routes

@app.route("/dna")
def dna():
    limit = max(1, min(request.args.get("n", DEFAULT_ROW_LIMIT, type=int), 20000))
    conn = _conn()
    try:
        r = rollups(conn)
        return render_dna(
            PAGE_T, r["dna"],
            platform=platform_stats(conn),
            network=r["network"],
            axis=r["dna"]["categories"],
            stations=r["stations"],
            genre_hex=r["genre_hex"],
            misses=r["misses"],
            rows=load_recent_rows(conn, limit),
            total_rows=total_rows(conn),
            pin_station=None,
        )
    finally:
        conn.close()


@app.route("/dna/station/<station>")
def dna_station(station):
    conn = _conn()
    try:
        dna_ = rollups(conn)["dna"]
    finally:
        conn.close()
    if dna_["totals"].get(station, 0) < station_stats.MIN_CATEGORIZED:
        return "", 404
    resp = app.make_response(render_dna(EMBED_T, dna_, pin_station=station))
    # so it can be iframed / fetched cross-origin from the other page
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers.pop("X-Frame-Options", None)  # or configure CSP frame-ancestors
    return resp


@app.route("/dna/data")
def dna_data():
    conn = _conn()
    try:
        resp = jsonify(rollups(conn)["dna"])
    finally:
        conn.close()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/dna/network")
def dna_network():
    """Network-wide genre / era / playcount distributions for the About page."""
    conn = _conn()
    try:
        # Copy, don't mutate the cached rollup. n_polls / first_poll count every
        # poll (identified or not), for the app's footer.
        first_poll, n_polls = conn.execute("SELECT MIN(ts), COUNT(*) FROM plays").fetchone()
        resp = jsonify(dict(rollups(conn)["network"], n_polls=n_polls, first_poll=first_poll))
    finally:
        conn.close()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/dna/songs/<station>")
def dna_songs(station):
    """A few random distinct songs identified on one station (station pop-up)."""
    n = max(1, min(request.args.get("n", 10, type=int), 20))
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT artist, title, MAX(COALESCE(SUBSTR(acr_release, 1, 4), mb_year)) AS year,"
            # most recent non-empty show for this song (ts sorts as text, so prefix it)
            "       MAX(CASE WHEN TRIM(COALESCE(show, '')) != '' THEN ts || char(31) || show END) AS last_show"
            "  FROM plays"
            " WHERE station = ? AND matched = 1"
            "   AND TRIM(COALESCE(artist, '')) != '' AND TRIM(COALESCE(title, '')) != ''"
            " GROUP BY LOWER(TRIM(artist)), LOWER(TRIM(title))"
            " ORDER BY RANDOM() LIMIT ?",
            (station, n),
        ).fetchall()
    finally:
        conn.close()
    fix = station_stats.fix_text   # in case old garbled rows haven't been repaired yet
    resp = jsonify([{"artist": fix(r["artist"]), "title": fix(r["title"]), "year": r["year"],
                     "show": fix(r["last_show"].split(chr(31), 1)[1]) if r["last_show"] else None}
                    for r in rows])
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


_match_cache = {}   # lowercased username -> (fetched_at, result)
MATCH_TTL = 3600


@app.route("/dna/daily")
def dna_daily():
    """
    Today's Daily Set. ?date=YYYY-MM-DD (the listener's local date)
    &anchor=<station they listen to most> (omit for new listeners)
    &exclude=<station> (repeatable: stations they already know)&n=6

    With &explain=<role>|<station> (repeatable) and the set's anchor, returns
    only {"explained": [...]}: fresh wording for picks the app already has.
    """
    date = (request.args.get("date") or "")[:10] or datetime.date.today().isoformat()
    anchor = request.args.get("anchor") or None
    exclude = request.args.getlist("exclude")
    explain = [e.split("|", 1) for e in request.args.getlist("explain") if "|" in e]
    n = max(1, min(request.args.get("n", 6, type=int), 12))
    conn = _conn()
    try: dna_ = rollups(conn)["dna"]
    finally: conn.close()
    if explain:
        resp = jsonify({"explained": station_stats.daily_explain(dna_, anchor, explain)})
        resp.headers["Access-Control-Allow-Origin"] = "*"
        resp.headers["Cache-Control"] = "no-store"
        return resp
    out = station_stats.daily_set(dna_, date, anchor, exclude, n)
    resp = jsonify(out or {})
    if out is None:
        resp.status_code = 404
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ---- song artwork + links (iTunes Search: free, no key), cached in the db

_track_links_lock = threading.Lock()


def _ensure_track_links(conn):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS track_links ("
        "  artist TEXT, title TEXT, artwork TEXT, apple_url TEXT, ts REAL,"
        "  PRIMARY KEY (artist, title))")


def _itunes_track(artist, title):
    """(artwork_url, apple_music_url) for a song, or (None, None)."""
    import requests
    try:
        r = requests.get("https://itunes.apple.com/search",
                         params={"term": f"{artist} {title}", "entity": "song", "limit": 1},
                         timeout=6)
        res = (r.json().get("results") or []) if r.ok else []
    except Exception:
        return None, None
    if not res:
        return None, None
    art = res[0].get("artworkUrl100")
    if art:
        art = art.replace("100x100bb", "600x600bb")
    return art, res[0].get("trackViewUrl")


def _track_links(conn, artist, title):
    """Cached iTunes lookup. Misses are cached too (for a week) so a song
    iTunes doesn't know isn't looked up on every request."""
    from urllib.parse import quote
    key = (artist.lower(), title.lower())
    with _track_links_lock:
        _ensure_track_links(conn)
        row = conn.execute("SELECT artwork, apple_url, ts FROM track_links WHERE artist = ? AND title = ?",
                           key).fetchone()
        if row is None or (row[0] is None and _time.time() - (row[2] or 0) > 7 * 86400):
            art, apple = _itunes_track(artist, title)
            conn.execute("INSERT OR REPLACE INTO track_links VALUES (?, ?, ?, ?, ?)",
                         (key[0], key[1], art, apple, _time.time()))
            conn.commit()
        else:
            art, apple = row[0], row[1]
    return {
        "artwork": art,
        "apple_music": apple,
        # No Spotify key needed: a search link opens the Spotify app on the song.
        "spotify": "https://open.spotify.com/search/" + quote(f"{artist} {title}"),
    }


@app.route("/dna/tracks/<station>")
def dna_tracks(station):
    """
    Three songs heard on a station for today's recs: popular, middle, deep.
    ?date=YYYY-MM-DD (listener's local date) keeps them steady all day.
    Each: tier, title, artist, year, category, playcount, artwork, apple_music, spotify.
    """
    date = (request.args.get("date") or "")[:10] or datetime.date.today().isoformat()
    conn = _conn()
    try:
        tracks = station_stats.daily_tracks(conn, station, date)
        for t in tracks:
            t.update(_track_links(conn, t["artist"], t["title"]))
    finally:
        conn.close()
    resp = jsonify(tracks)
    if not tracks:
        resp.status_code = 404
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/dna/similar/<station>")
def dna_similar(station):
    """You Might Like for one station (shared by the site and the app). ?n= (default 30)."""
    n = max(1, min(request.args.get("n", 30, type=int), 100))
    conn = _conn()
    try:
        dna_ = rollups(conn)["dna"]
    finally:
        conn.close()
    if station not in dna_["radar"]:
        resp = jsonify([]); resp.status_code = 404
    else:
        resp = jsonify(station_stats.similar_stations(dna_, station, n))
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/dna/match")
def dna_match():
    """Find-your-station: ?user=<Last.fm username>."""
    user = (request.args.get("user") or "").strip()
    key = user.lower()
    hit = _match_cache.get(key)
    if hit and _time.time() - hit[0] < MATCH_TTL:
        resp = jsonify(hit[1])
    else:
        conn = _conn()
        try:
            profile = radio_match.listener_profile(conn, user)
            result = radio_match.match(conn, rollups(conn)["dna"], profile)
            _match_cache[key] = (_time.time(), result)
            resp = jsonify(result)
        except radio_match.MatchError as e:
            resp = jsonify({"error": str(e)}); resp.status_code = 400
        except radio_match.ConfigError:
            app.logger.exception("match not configured")
            resp = jsonify({"error": "Matching isn't switched on yet. Check back soon."}); resp.status_code = 503
        except Exception as e:   # Last.fm down, timeouts, ...
            app.logger.exception("match failed")
            resp = jsonify({"error": "Couldn't reach Last.fm right now. Try again in a minute."}); resp.status_code = 502
        finally:
            conn.close()
    resp.headers["Access-Control-Allow-Origin"] = "*"
    return resp


@app.route("/dna/stations.csv")
def dna_stations_csv():
    conn = _conn()
    try:
        stations = rollups(conn)["stations"]
        axis = rollups(conn)["dna"]["categories"]
    finally:
        conn.close()
    if not stations:
        return csv_response(["station"], [], "stations.csv")

    base = [k for k in stations[0] if k not in ("genres", "cells", "computed_at")]
    header = base + [f"pct_{c}" for c in axis]
    rows = ([s[k] for k in base] + [s["genres"][c] for c in axis] for s in stations)
    return csv_response(header, rows, "stations.csv")


@app.route("/dna/tags.csv")
def dna_tags_csv():
    """Uncategorized tags + a blank category column, ready to be filled in."""
    min_n = request.args.get("min", 1, type=int)
    conn = _conn()
    try:
        rows = [(tag, n, "") for tag, n in station_stats.uncategorized(conn, min_n)]
    finally:
        conn.close()
    return csv_response(["tag", "count", "category"], rows, "uncategorized-tags.csv")


@app.route("/dna/categories.csv")
def dna_categories_csv():
    """The existing category vocabulary, to check mappings against."""
    return csv_response(["category"], ((c,) for c in genres.all_categories()),
                        "categories.csv")


@app.route("/dna/plays.csv")
def dna_plays_csv():
    """Full poll export — not capped, unlike the on-page table."""
    conn = _conn()
    try:
        cur = conn.execute(f"SELECT {TABLE_COLS} FROM plays ORDER BY ts DESC")
        header = [d[0] for d in cur.description]
        rows = [tuple(r) for r in cur]
    finally:
        conn.close()
    return csv_response(header, rows, "plays.csv")


ensure_indexes()