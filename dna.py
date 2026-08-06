# dna.py
import sqlite3
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
  table{border-collapse:collapse;width:100%}
  th,td{text-align:left;padding:4px 10px;border-bottom:1px solid #eee;white-space:nowrap}
  th{position:sticky;top:0;background:#fff;border-bottom:2px solid #ccc}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  tr:hover{background:#fafafa}
  .miss{color:#999}
</style>
<h1>Recent plays <small>({{rows|length}} shown)</small></h1>
<table>
  <tr>
    <th>time (UTC)</th><th>station</th><th>source</th>
    <th>artist</th><th>title</th><th>genre</th><th>year</th><th class=num>last.fm plays</th>
  </tr>
  {% for r in rows %}
  <tr class="{{ 'miss' if not r['matched'] else '' }}">
    <td>{{ r['ts'][:19].replace('T',' ') }}</td>
    <td>{{ r['station'] }}</td>
    <td>{{ r['source'] }}</td>
    <td>{{ r['artist'] or '' }}</td>
    <td>{{ r['title'] or '' }}</td>
    <td>{{ r['acr_genres'] or r['mb_genre'] or r['lf_tags'] or '' }}</td>
    <td>{{ r['acr_release'][:4] if r['acr_release'] else (r['mb_year'] or '') }}</td>
    <td class=num>{{ '{:,}'.format(r['lf_playcount']) if r['lf_playcount'] else '' }}</td>
  </tr>
  {% endfor %}
</table>
"""

@app.route("/dna")
def dna():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM plays ORDER BY ts DESC LIMIT 500"
    ).fetchall()
    conn.close()
    return render_template_string(PAGE, rows=rows)