import concurrent.futures
from tqdm import tqdm
import requests
import json

with open('cri_ids.json', 'r') as f:
    cri_curr = json.load(f)

list_resp = requests.get('https://api.community-radio-index.com/api/radios/').json()
station_base = 'https://api.community-radio-index.com/api/radios/'
station_resp = requests.get(station_base + list_resp[0]['id']).json()
untracked_stations = [i for i in list_resp if i['id'] not in cri_curr.values()]

cri = {}
max_threads = 20 

def fetch_data(i):
    session = requests.Session()
    item_id = i['id']
    try:
        response = session.get(station_base + item_id).json()
        return item_id, response
    except Exception as e:
        print(f"Error fetching {item_id}: {e}")
        return item_id, None

with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
    results = list(tqdm(executor.map(fetch_data, list_resp), total=len(list_resp)))

for item_id, response in results:
    if response is not None:
        cri[item_id] = response

one_radio = requests.get('https://one.radio/info').json()
one_radio_websites = [v['mainLink'] for k,v in one_radio.items()]
one_radio_streams = [v['streamLink'] for k,v in one_radio.items()]
untracked_live_stations = [v for _,v in cri.items() if v['id'] not in cri_curr.values() and v['stream_url']!='']

import re
from urllib.parse import urlparse

def norm_url(u):
    if not u:
        return None
    p = urlparse(u.strip().lower())
    host = p.netloc.removeprefix("www.")
    path = p.path.rstrip("/")
    return f"{host}{path}" or None

def norm_name(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower()) or None

# Build reverse lookups: normalized value -> one_radio station name
by_website, by_stream, by_name = {}, {}, {}
for name, v in one_radio.items():
    if (k := norm_url(v.get("mainLink"))):
        by_website.setdefault(k, name)
    if (k := norm_url(v.get("streamLink"))):
        by_stream.setdefault(k, name)
    if (k := norm_name(name)):
        by_name.setdefault(k, name)

add_cri_id = {}
remaining = []

for station in untracked_live_stations:
    match = (
        by_website.get(norm_url(station.get("website_url")))
        or by_stream.get(norm_url(station.get("stream_url")))
        or by_name.get(norm_name(station.get("name")))
    )
    if match:
        if not one_radio[match].get('criId'):
            add_cri_id[match] = station["id"]
    else:
        remaining.append(station)

cri_curr.update(add_cri_id)
with open('cri_ids.json', 'w') as f:
    json.dump(cri_curr, f)

untracked_live_stations = remaining

AUDIO_TYPES = ("audio/", "application/ogg", "video/mp2t", "application/vnd.apple.mpegurl", "application/x-mpegurl")

def check_live(station, timeout=7, min_bytes=8192):
    url = station['stream_url']
    try:
        with requests.get(url, stream=True, timeout=timeout,
                          headers={"Icy-MetaData": "1", "User-Agent": "Mozilla/5.0"}) as r:
            if r.status_code != 200:
                return False

            ctype = r.headers.get("Content-Type", "").lower()
            if not ctype.startswith(AUDIO_TYPES):
                return False

            read = 0
            for chunk in r.iter_content(1024):
                read += len(chunk)
                if read >= min_bytes:
                    return True
            return False
    except requests.RequestException:
        return False
    
with concurrent.futures.ThreadPoolExecutor(max_workers=max_threads) as executor:
    results = list(tqdm(executor.map(check_live, untracked_live_stations), total=len(untracked_live_stations)))

truly_live_untracked_stations = []
for s,r in zip(untracked_live_stations,results):
    if r:
        truly_live_untracked_stations.append(s)

with open('untracked.json', 'w') as f:
    json.dump(truly_live_untracked_stations, f)