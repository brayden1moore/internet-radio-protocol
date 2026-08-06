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
  th{position:sticky;top:0;background:#fff;border-bottom:2px solid #ccc}
  td.num{text-align:right;font-variant-numeric:tabular-nums}
  tr:hover{background:#fafafa}
  .miss{color:#999}

  /* summary table column hints */
  table.summary td, table.summary th{white-space:nowrap}
  table.summary td.txt{white-space:normal}

  /* plays table: fixed widths so nothing overflows */
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
  table.plays td{white-space:nowrap}      /* ellipsis-truncate long cells */
  table.plays td.wrap{white-space:normal} /* let these wrap instead */
</style>

<h1>One Radio DNA</h1>

<h2>Per-station summary <small>({{summaries|length}} stations)</small></h2>
<table class="summary">
  <tr>
    <th>station</th><th class=num>polled</th><th class=num>id'd</th><th class=num>id rate</th>
    <th>top artist</th><th class=num>avg yr</th><th class=num>yr stdev</th>
    <th>top genre</th><th class=num>avg plays</th><th class=txt>most popular</th><th class=txt>least popular</th>
  </tr>
  {% for s in summaries %}
  <tr>
    <td>{{ s.station }}</td>
    <td class=num>{{ '{:,}'.format(s.total) }}</td>
    <td class=num>{{ '{:,}'.format(s.identified) }}</td>
    <td class=num>{{ '%.0f'|format(s.id_rate) }}%</td>
    <td>{{ s.top_artist }}{% if s.top_artist_n %} ({{ s.top_artist_n }}){% endif %}</td>
    <td class=num>{{ s.avg_year or '—' }}</td>
    <td class=num>{{ s.year_stdev or '—' }}</td>
    <td>{{ s.top_genre }}{% if s.top_genre_n %} ({{ s.top_genre_n }}){% endif %}</td>
    <td class=num>{{ '{:,}'.format(s.avg_plays) if s.avg_plays else '—' }}</td>
    <td class=txt>{{ s.most_popular }}</td>
    <td class=txt>{{ s.least_popular }}</td>
  </tr>
  {% endfor %}
</table>

<h2>Recent plays <small>({{rows|length}} shown)</small></h2>
<table class="plays">
  <tr>
    <th class=c-time>time (UTC)</th><th class=c-station>station</th><th class=c-source>source</th>
    <th class=c-artist>artist</th><th class=c-title>title</th><th class=c-label>label</th>
    <th class=c-genre>genre</th><th class=c-year>year</th><th class="c-plays num">last.fm plays</th>
  </tr>
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
</table>
"""