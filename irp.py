from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from shazamio import Shazam, Serialize
from bs4 import BeautifulSoup
import subprocess
import traceback
import requests
import tempfile
import asyncio
import logging
import shutil
import random
import time
import json
import re
import io

logging.disable()

def _dst_bounds(year):
    for d in range(8, 15):
        if date(year, 3, d).weekday() == 6:
            start = datetime(year, 3, d, 2, tzinfo=timezone.utc)
            break
    for d in range(1, 8):
        if date(year, 11, d).weekday() == 6:
            end = datetime(year, 11, d, 2, tzinfo=timezone.utc)
            break
    return start, end

def get_latest_time(streams):
    latest_utc = datetime.min.replace(tzinfo=timezone.utc)
    latest_name = None

    for name, data in streams.items():
        ts = data.get('lastUpdated')
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if isinstance(ts, datetime):
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts > latest_utc:
                latest_utc, latest_name = ts, name

    if not latest_name:
        return None, None, None, None

    start, end = _dst_bounds(latest_utc.year)
    in_dst = start <= latest_utc < end

    pt_offset = -7 if in_dst else -8
    et_offset = -4 if in_dst else -5

    PST = timezone(timedelta(hours=pt_offset))
    EST = timezone(timedelta(hours=et_offset))

    latest_pt = latest_utc.astimezone(PST)
    latest_et = latest_utc.astimezone(EST)
    return latest_utc, latest_pt, latest_et, latest_name

def write_main_page(streams):
    latest_time_utc, latest_time_pt, latest_time_et, latest_name = get_latest_time(streams)
    
    offline = []
    online = []
    rerun = []
    for k, v in streams.items():
        if v['status'] == 'Offline':
            offline.append(v)
        elif any(i in v.get('oneLiner').lower() for i in ['re-run','re-wav','restream','playlist']):
            rerun.append(v)
        else:
            online.append(v)
    
    random.shuffle(online)
    streams =  online + rerun + offline

    main_text = ''.join(
        ['<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1"><meta charset="UTF-8"><title>Internet Radio Protocol</title><link rel="icon" href="assets/icon-dark.ico" type="image/x-icon"><link rel="shortcut icon" href="assets/icon-dark.ico" type="image/x-icon"><link rel="apple-touch-icon" href="assets/icon-dark.png"></head><body style="font-family:Andale Mono; padding:10vw; padding-top:10px;"><div style="display:flex; justify-content:center"><img src="assets/scudradiocenter.gif" alt="Loading" height="300px" width="auto"></div>',
        '<div class="the-header">LISTEN TO<br>COMMUNITY RADIO<br>EVERY DAY</div>', 
        "I love internet radio, so I'm putting it all in one place, like radio-radio. The Internet Radio Protocol is a simple, standardized hub of real-time now playing data and direct streaming links for an ever-expanding list of internet radio stations. Click to tune in. Follow me on instagram, <a target='_blank' href='https://www.instagram.com/scudhouse/'>@scudhouse</a>.",
        '', '',
        '<div class="streams-container">',
        ''.join([f'''<div id="{v['name']}" onclick="toggleAudio('{v['name']}')" style="cursor:pointer; background-color: #FFFFFF; color:#000000; height: 110px; padding: 10px; overflow-x:scroll; overflow-y:hidden; border:1px solid black; align-items: center; display: flex; white-space: nowrap;">
        <img width="110px" height="110px" style="margin-right:10px; border: 1px solid black; cursor: pointer; flex-shrink: 0;"
        src="{v["logo"]}"  />
        <div style="font-size:10pt; white-space: nowrap; flex-shrink: 0;">
        <a target="_blank" href="{v['mainLink']}">{v['name']}</a><br><br>Now Playing: {v.get('oneLiner')}<br>Location: {v["location"]}<br>Status: {v["status"]}<br>Last Updated: <span class="last-updated" data-utc="{v['lastUpdated']}">{v['lastUpdated']}</span><br>
        <audio id="{v['name']}-audio" style="width:40px;" data-src="{v["streamLink"]}"></audio>
        </div>
        </div>''' for v in streams]),
        '</div>',
        '',
        '',
        'You can access this information and more in JSON format at <a href="https://internetradioprotocol.org/info">internetradioprotocol.org/info</a>. The list currently includes:<br><br>',
        '',
        ", ".join(list(streams[0].keys())) + '.',
        '',
        '<br><br>If you have any questions, comments, or radio station addition suggestions, please email <a href="mailto:brayden@braydenmoore.com">brayden@braydenmoore.com</a>. Also, check out the tuner I am making (I know it is still very crude!):<br><br>',
        '<a href="https://www.instagram.com/p/DLncaEiys_R/" target="_blank"><img height=250px style="border: 1px solid black;" src="assets/tuner.jpg"></a>',
        '</body></html>',
        '<style>body {background-color: #FFFF00;}</style>',
        '<style>.the-header {font-family: "Arial Black"; font-size: 24pt; line-height:1em; margin-bottom:20px;}</style>',
        '<style> @font-face {font-family: "Arial Black";src: url("assets/Arial Black.ttf") format("truetype");}</style>',
        '<style>a {font-size: 12pt; color:#000000; border-bottom: 1px solid black; text-decoration: none;}</style>',
        '<style>a:hover {background-color: #000000; color:#FFFFFF}</style>',
        '<style> @font-face {font-family: "Andale Mono";src: url("assets/andalemono.ttf") format("truetype");}</style>',
        '<style>@keyframes pulse{0%{background:#ffffff}50%{background:#ddd}100%{background:##ffffff}}.pulsing{animation:pulse 1s infinite}</style>',
        '<style>.streams-container {display: grid; grid-template-columns: 1fr; gap: 20px; margin-top:30px; margin-bottom:30px;}</style>',
        '<style>@media (orientation: landscape) {.streams-container {grid-template-columns: 1fr 1fr;}}</style>',
        #'<script id="cid0020000408410894191" data-cfasync="false" async src="//st.chatango.com/js/gz/emb.js" style="width: 277px;height: 408px;">{"handle":"internetradioprotoco","arch":"js","styles":{"a":"000000","b":100,"c":"FFFFFF","d":"FFFFFF","k":"000000","l":"000000","m":"000000","n":"FFFFFF","p":"10","q":"000000","r":100,"fwtickm":1}}</script>'
        "<script>function toggleAudio(id){let a=document.getElementById(`${id}-audio`),d=document.getElementById(id),isPlaying=d.style.backgroundColor==='yellow';document.querySelectorAll('audio').forEach(e=>{e.pause();e.removeAttribute('src');e.load();e.parentElement.parentElement.style.backgroundColor='white';e.parentElement.parentElement.classList.remove('pulsing')});if(!isPlaying){a.src=a.dataset.src;a.load();d.classList.add('pulsing');a.play().then(()=>{d.classList.remove('pulsing');d.style.backgroundColor='yellow'}).catch(e=>{console.error(e);d.classList.remove('pulsing')})}}</script>",        
        "<script>document.querySelectorAll('.last-updated').forEach(el => {const utcStr = el.dataset.utc;if (utcStr) {const date = new Date(utcStr);if (!isNaN(date)) {el.textContent = date.toLocaleString();}}});</script>"]
    )
    with open('index.html', 'w') as f:
        f.write(main_text)

def clean_text(text):
    cleaned_text = re.sub(r'<[^>]+>', '', text
                        ).replace('\xa0',' '
                        ).replace('\n',' '
                        ).replace('\r',''
                        ).replace('&amp;','&'
                        ).replace('  ',' '
                        ).replace('\u2019', "'"
                        ).replace('\u2013', "-"
                        ).replace('&#039;',"'"
                        ).replace('\u201c','"'
                        ).replace('\u201d','"'
                        ).strip()
    return cleaned_text

def s(number):
    if number == 1:
        return ''
    else:
        return 's'

class Stream:
    def __init__(self, from_dict=None, name=None, logo=None, location=None, info_link=None, stream_link=None, main_link=None, about=None):
        self.name = name
        self.logo = logo
        self.location = location
        self.info_link = info_link
        self.stream_link = stream_link
        self.main_link = main_link
        self.about = about
        self.status = "Online"
        self.now_playing_artist = None
        self.now_playing = None
        self.now_playing_subtitle = None
        self.now_playing_description = None
        self.now_playing_description_long = None
        self.additional_info = None
        self.show_logo = None
        self.insta_link = None
        self.bandcamp_link = None
        self.soundcloud_link = None
        self.last_updated = None
        self.shazam_guess = None
        self.one_liner = None

        if isinstance(from_dict, dict):
            self.name = from_dict.get('name')
            self.logo = from_dict.get('logo')
            self.location = from_dict.get('location')
            self.info_link = from_dict.get('infoLink')
            self.stream_link = from_dict.get('streamLink')
            self.main_link = from_dict.get('mainLink')
            self.about = from_dict.get('about')
            self.status = from_dict.get('status')
            self.now_playing_artist = from_dict.get('nowPlayingArtist')
            self.now_playing = from_dict.get('nowPlaying')
            self.now_playing_subtitle = from_dict.get('nowPlayingSubtitle')
            self.now_playing_description = from_dict.get('nowPlayingDescription')
            self.now_playing_description_long = from_dict.get('nowPlayingDescriptionLong')
            self.additional_info = from_dict.get('nowPlayingAdditionalInfo')
            self.show_logo = from_dict.get('showLogo')
            self.insta_link = from_dict.get('instaLink')
            self.bandcamp_link = from_dict.get('bandcampLink')
            self.soundcloud_link = from_dict.get('soundcloudLink')
            self.last_updated = from_dict.get('lastUpdated')
            self.shazam_guess = from_dict.get('shazamGuess')
            self.one_liner = self.one_liner

    def to_dict(self):
        return {
            "name": self.name,
            "logo": self.logo,
            "about": self.about,
            "location": self.location,
            "status": self.status,

            "infoLink": self.info_link,
            "streamLink": self.stream_link,
            "mainLink": self.main_link,
            "showLogo": self.show_logo,

            "nowPlaying": self.now_playing,
            "nowPlayingSubtitle": self.now_playing_subtitle,
            "nowPlayingArtist": self.now_playing_artist,
            "nowPlayingDescription": self.now_playing_description,
            "nowPlayingDescriptionLong": self.now_playing_description_long,
            "nowPlayingAdditionalInfo": self.additional_info,

            "bandcampLink": self.bandcamp_link,
            "soundcloudLink": self.soundcloud_link,
            "instaLink": self.insta_link,

            "shazamGuess": self.shazam_guess,

            "lastUpdated": self.last_updated,

            "oneLiner":self.one_liner
        }
    
    def update(self):
        if "internetradioprotocol.org" not in self.logo:
            self.logo = "https://internetradioprotocol.org/" + self.logo

        if self.name in ['HydeFM','SutroFM','Lower Grand Radio']:
            info = requests.get(self.info_link).json()
            self.now_playing = None
            self.now_playing_artist = None
            try: 
                self.now_playing_artist = info['name'].strip().split(' w/ ')[1] # artist name like "Vitamin 1K (Benji)"
                self.now_playing = info['name'].strip().split(' w/ ')[0] # show name like "Super Supplement"
            except:
                self.now_playing = info.get('name', self.name).strip() # full title like "Super Supplement w/ Vitamin 1k (Benji)"
                self.now_playing_artist = None
            try:
                self.additional_info = f"{info['listeners']} listener{s(info['listeners'])}" # listener count 
            except:
                self.additional_info = None
            self.status = "Online" if info['online'] == True else "Offline"
            if self.status == "Offline":
                self.now_playing = None
                self.now_playing_artist = None
                self.additional_info = None

        elif 'NTS' in self.name:
            info = requests.get(self.info_link).json()
            result_idx = 0 if self.name == 'NTS 1' else 1

            now = info['results'][result_idx]['now']
            self.now_playing = clean_text(now['broadcast_title']) # show name like "In Focus: Timbaland"
            self.location = now['embeds']['details']['location_long'] # location like "New York"
            if not self.location:
                self.location = 'London'
            self.show_logo = now['embeds']['details']['media']['background_large'] or self.show_logo # show-specific logo if provided
            try:
                self.now_playing_description_long =  clean_text(now['embeds']['details']['description']) # full description
                self.now_playing_description =  clean_text(now['embeds']['details']['description'])[:44] + '...' # abridged description
            except:
                self.now_playing_description_long = None
                self.now_playing_description = None
                pass
            
            genres = []
            for g in now['embeds']['details']['genres']:
                genres.append(g['value'].strip())

            self.additional_info = ', '.join(genres) # genre list if provided

            self.insta_link = None
            self.bandcamp_link = None
            self.soundcloud_link = None
            for l in now['embeds']['details']['external_links']: # various external links
                if 'instagram.' in l.lower():
                    self.insta_link = l
                elif 'bandcamp.' in l.lower():
                    self.bandcamp_link = l
                elif 'soundcloud.' in l.lower():
                    self.soundcloud_link = l


        elif self.name == 'Dublab':
            now = datetime.now(timezone.utc)
            info = requests.get(self.info_link).json()

            for program in info:
                if datetime.fromisoformat(program['startTime']) < now:
                    self.now_playing = program['eventTitleMeta']['eventName'] # show name like "Dying Songs"
                    self.now_playing_artist = program['eventTitleMeta']['artist'] if program['eventTitleMeta']['artist'] else "Dublab" # artist name if provided lile "Jimmy Tamborello"
                    try:
                        self.show_logo = program['attachments'] or self.show_logo # show-specific logo if provided
                    except:
                        self.show_logo = None
                    try:
                        self.now_playing_description_long = clean_text(program['description']) # long description of the show
                        self.now_playing_description = clean_text(program['description'])[:44] + '...'  # abridged description
                    except:
                        self.now_playing_description_long = None
                        self.now_playing_description = None
                        pass

            
        elif self.name == 'WNYU':
            schedule = requests.get(self.info_link).json()
            id = schedule[0]['id']
            description_url = f'https://wnyu.org/v1/schedule/{id}'
            info = requests.get(description_url).json()
            self.now_playing = clean_text(schedule[0]['program']['name']) # show name like "The New Evening Show"
            self.additional_info = ', '.join([i.title() for i in info['episode']['genre_list']]) # genre list if provided
            self.show_logo = info['episode']['program']['image']['large']['url'] or self.show_logo # show-specific logo if provided
            try:
                self.now_playing_description_long = clean_text(info['episode']['description']) # blurb like "An eclectic mix of rock and related music. Etc etc"
                self.now_playing_description = clean_text(self.now_playing_description_long)[:44] + '...' # first sentence of the blurb
            except:
                self.now_playing_description_long = None
                self.now_playing_description = None
                pass


        elif self.name == 'Voices Radio': 
            info = requests.get(self.info_link).json()
            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # just artist name if possible like "Willow"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[0]) # just show name if posible like "Wispy"
                except:
                    self.now_playing_artist = None
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ','').replace('.mp3','')) # full title like "Wispy w/ Willow"


        elif self.name == 'Kiosk Radio': 
            info = requests.get(self.info_link).json()
            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
                self.now_playing_subtitle = None
            else:
                self.now_playing  = clean_text(info['shows']['current']['name']) # broadcast name like "Staff Picks" or "Piffy (live)"
                self.status = 'Online'
                try:
                    self.now_playing_artist  = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # artist names like "Fa_Fane & F.M."
                    self.now_playing_subtitle = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[0]) # episode title "Delodio"
                except:
                    self.now_playing_artist = None
                    self.now_playing_subtitle = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','')) # full title like "Badlcukwind plays Drowned By Locals"'


        elif self.name == 'Do!!You!!! World': 
            info = requests.get(self.info_link).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # artist name like "Charlemagne Eagle"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split('w/')[0]) # show name like "The Do!You!!! Breakfast Show"
                except:
                    self.now_playing_artist = None
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','')) # show name like "The Do!You!!! Breakfast Show w/ Charlemagne Eagle"

        elif self.name == 'Radio Quantica':
            info = requests.get(self.info_link).json()

            self.now_playing = info['currentShow'][0]['name'] # show name like "NIGHT MOVES"
            try:
                self.now_playing_subtitle = info['current']['name'] # track name if provided
                self.now_playing_subtitle = None
            except: 
                pass

        elif self.name == "Bloop Radio":
            payload = {
                'action': 'show-time-curd',
                'crud-action': 'read',
                'read-type': 'current'
            }
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'Mozilla/5.0'
            }
            response = requests.post(self.info_link, data=payload, headers=headers).json()
            try:
                self.now_playing = response['current-show']['showName'] # full show name
            except:
                self.now_playing = 'Re-Run' # rather than "REPEATS UNTIL..."

        elif self.name == "The Lot Radio":
            api_key = 'AIzaSyD7jIVZog7IC--y1RBCiLuUmxEDeBH9wDA'
            calendar_id = self.info_link
            time_minus_1hr = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()

            url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events'
            params = {
                'key': api_key,
                'maxResults': 3,
                'singleEvents': True,
                'orderBy': 'startTime',
                'timeMin': time_minus_1hr
            }

            response = requests.get(url, params=params)
            data = response.json()

            for event in data.get('items', []):
                end_time_str = event['end']['dateTime']
                end_time = datetime.fromisoformat(end_time_str)

                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str)
                now_utc = datetime.now(timezone.utc)

                if end_time > now_utc > start_time:
                    self.now_playing = event['summary']
                    try:
                        description_lines = event['description'].replace('&nbsp;','<br>').replace('\n','<br>').split('<br>')
                        self.now_playing_description_long = clean_text(description_lines[0]) # long desc 
                        self.now_playing_description = self.now_playing_description_long[:44] + '...'# short desc like "A late night special with Kem Kem playing from the heart ..."
                        self.additional_info = clean_text(description_lines[-1]) # genre list like "World, Jazz, Afrobeats, Electronic"
                        
                        self.insta_link = None
                        self.bandcamp_link = None
                        self.soundcloud_link = None
                        for l in description_lines:
                            l = clean_text(l)
                            if 'instagram.' in l.lower():
                                self.insta_link = l
                            elif 'bandcamp.' in l.lower():
                                self.bandcamp_link = l
                            elif 'soundcloud.' in l.lower():
                                self.soundcloud_link = l   
                    except:
                        self.now_playing_description = None
                        self.now_playing_description_long = None
                        self.additional_info = None
                        pass

        elif self.name == 'Internet Public Radio':
            info = requests.get(self.info_link).json()
            self.now_playing = info['nowplaying']
            
        elif self.name == 'KQED':
            today = date.today().isoformat()
            epoch_time = int(time.time())
            info = requests.get(self.info_link + today).json()
            programs = info['data']['attributes']['schedule']

            for program in programs:
                if int(program['startTime']) < epoch_time:
                    self.now_playing = program['programTitle'] # broader series title like "Climate One"
                    self.now_playing_subtitle = program['episodeTitle'] # specific episode title like "Gina McCarthy on Cutting Everything but Emissions"
                    self.additional_info = program['programSource'] # sometimes NPR or BBC
                    try:
                        self.now_playing_description = clean_text(program['programDescription'])[:44] + '...' # series description like "The Trump administration has been dismantlin..."
                        self.now_playing_description_long = clean_text(program['programDescription']) # full series description
                    except:
                        self.now_playing_description = None
                        self.now_playing_description_long = None
                        pass

        elif self.name == 'We Are Various':
            info = requests.get(self.info_link).json()
            self.status = 'Online' if info['is_online'] == True else 'Offline'
            self.additional_info = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['title'] # simple show title

        elif self.name == 'KJazz':
            webpage = requests.get(self.main_link).text
            soup = BeautifulSoup(webpage, 'html.parser')
            self.now_playing = soup.find_all("a", "noDec")[1].get_text() # host name
            self.now_playing_artist = None

        elif self.name == 'KEXP':
            now_utc = datetime.now(timezone.utc)
            song = requests.get(self.info_link).json()['results'][0]
            show_uri = song['show_uri']
            show = requests.get(show_uri).json()

            self.now_playing_artist = ', '.join(show['host_names']) # concatenation of host names
            self.now_playing = show['program_name'] # concatenation of host names show name
            self.now_playing_additional_info = show['program_tags'] # genre list
            self.show_logo = show['program_image_uri'] # show logo if provided
            self.now_playing_subtitle = None
            if song['play_type'] == 'trackplay':
                self.now_playing_subtitle = f"{song['song']} by {song['artist']}" # last played song and artist
        
        elif self.name == 'Clyde Built Radio':
            info = requests.get(self.info_link).json()
            try:
                self.now_playing = info['shows']['current']['name'] # just song name
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'SF 10-33':
            info = requests.get(self.info_link).json()
            self.now_playing = info['songs'][0]['title']
            self.now_playing_artist = info['songs'][0]['artist']
            self.now_playing_subtitle = info['songs'][0]['album']
        
        elif self.name == 'SomaFM Live':
            info = requests.get(self.info_link).json()
            self.now_playing = info['songs'][0]['title']
            self.now_playing_artist = info['songs'][0]['artist']
            self.now_playing_subtitle = info['songs'][0]['album']

        elif self.name in ['Rinse UK','Rinse FR','SWU FM','Kool FM']:
            name_to_slug_dict = {
                'Rinse UK':'uk',
                'Rinse FR':'france',
                'SWU FM':'swu',
                'Kool FM':'kool'
            }

            info = requests.get(self.info_link).json()
            now_utc = datetime.now(timezone.utc)
            shows = info['channels']
            episodes = [i for i in info['episodes'] if i['channel'][0]['slug'] == name_to_slug_dict[self.name]]

            for i in episodes:
                episode_time = datetime.fromisoformat(i['episodeTime']) 
                episode_date = datetime.fromisoformat(i['episodeDate']) + timedelta(minutes=60)

                episode_length = i.get('episodeLength') or 120
                episode_end = episode_time + timedelta(minutes=episode_length)

                if (episode_time <= now_utc <= episode_end) & (episode_date.date() == now_utc.date()):
                    self.now_playing = i['title']
                    self.now_playing_subtitle = i['subtitle']
                
                    try:
                        self.additional_info = ', '.join([i['title'] for i in i['parentShow'][0]['genreTag']])
                    except:
                        self.additional_info = None
                        pass
                    try:
                        self.now_playing_description_long = i['parentShow'][0]['extract']
                        self.now_playing_description = i['parentShow'][0]['extract'][:44] + '...'
                    except:
                        self.now_playing_description_long = None
                        self.now_playing_description = None
                        pass
                    try:
                        self.show_logo = f"https://img.imageboss.me/rinse-fm/cover:smart/600x600/{i['featuredImage'][0]['filename']}"
                    except:
                        self.show_logo = None
                        pass

        elif self.name == 'Radio Sygma':
            info = requests.get(self.info_link).json()
            self.now_playing = info['tracks']['current']['metadata']['track_title']

        elif self.name == 'LYL Radio':
            info = requests.post(self.info_link,data={"variables":{},"query":"{\n  onair {\n    title\n    hls\n    __typename\n  }\n}\n"})
            try:
                self.now_playing = info.json()['data']['onair']['title']
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'
        
        elif self.name == 'Skylab Radio':
            info = requests.get(self.info_link).json()['current']

            self.now_playing = info['metadata']['track_title']
            self.now_playing_artist = info['metadata']['artist_name']

            try:
                self.show_logo = info['metadata']['artwork_url']
            except:
                self.show_logo = None
        
        elif self.name == 'BFF.fm':
            info = requests.get(self.info_link).json()
            self.now_playing = info['program']
            self.now_playing_artist = info['presenter']
            self.now_playing_subtitle = info['title'] + ' by ' + info['artist']
            try:
                self.show_logo = info['program_image'].replace('\/','/')
            except:
                self.show_logo = None

        elif self.name == 'Fault Radio':
            api_key = 'AIzaSyDU4MOqK7SVbAtcXtaICsIZVyECmLWK6Dw'
            calendar_id = self.info_link
            time_minus_1hr = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()

            url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events'
            params = {
                'key': api_key,
                'maxResults': 3,
                'singleEvents': True,
                'orderBy': 'startTime',
                'timeMin': time_minus_1hr
            }

            response = requests.get(url, params=params)
            data = response.json()

            self.status = 'Offline'
            self.now_playing = None
            for event in data.get('items', []):
                end_time_str = event['end']['dateTime']
                end_time = datetime.fromisoformat(end_time_str)

                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str)
                now_utc = datetime.now(timezone.utc)

                if end_time > now_utc > start_time:
                    self.status = 'Online'
                    self.now_playing = event['summary']


    def guess_shazam(self):
        self.shazam_guess = "Unknown"
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
                temp_path = tmp.name
            subprocess.run([
                'ffmpeg', '-y',
                '-i', self.stream_link,
                '-t', '3',
                '-f', 'wav',
                '-ar', '44100',
                '-ac', '1',
                temp_path
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(Shazam().recognize(temp_path))

            track_id = result['matches'][0]['id']
            about_track = loop.run_until_complete(Shazam().track_about(track_id=track_id))
            serialized = Serialize.track(data=about_track)
            self.shazam_guess = f"{serialized.title} by {serialized.subtitle}"
        except Exception:
            print(f"[shazam error] {self.stream_link}")
            traceback.print_exc()

    def set_last_updated(self):
        self.last_updated = datetime.now(timezone.utc)

    def update_one_line(self):
        parts = [
            self.now_playing,
            self.now_playing_artist,
            self.now_playing_subtitle,
            self.additional_info,
        ]
        return_string = " - ".join(p for p in parts if p)
        if len(return_string) > 100:
            return_string = return_string[:100] + '...'
        self.one_liner = return_string

async def process_stream(name, value):
    stream = Stream(from_dict=value)
    try:
        stream.update()

        stream.shazam_guess = None
        #loop = asyncio.get_event_loop()
        #await loop.run_in_executor(None, stream.guess_shazam)

        stream.update_one_line()
        updated_dict = stream.to_dict()
        stream.set_last_updated()
        return (stream.name, stream.to_dict())
    except Exception:
        error = f'[{datetime.now()}] Error updating {stream.name}:\n{traceback.format_exc()}\n'
        return (stream.name, value, error)

async def main_loop():
    while True:
        with open('info.json', 'r') as f:
            stream_json = json.load(f)

        write_main_page(stream_json)

        tasks = [process_stream(name, val) for name, val in stream_json.items()]
        results = await asyncio.gather(*tasks)

        error_lines = []
        updated = {}

        for result in results:
            if len(result) == 3:
                name, val, err = result
                error_lines.append(err)
            else:
                name, val = result
            updated[name] = val

        with open('info.json', 'w') as f:
            json.dump(updated, f, indent=4, sort_keys=True, default=str)

        with open('errorlog.txt', 'w') as log:
            log.writelines(error_lines)

        write_main_page(updated)
        await asyncio.sleep(60)

if __name__ == '__main__':
    asyncio.run(main_loop())