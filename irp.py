from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from websocket import create_connection
from urllib.parse import quote, urlsplit, urlunsplit
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
import urllib.request, json
from io import BytesIO
from PIL import Image
import subprocess
import traceback
import requests
import tempfile
import asyncio
import logging
import shutil
import random
import pickle
import time
import json
import pytz
import re
import io
import os

logging.disable()

TIMEOUT = 15

with open('cri_ids.json','r') as f:
    cri = json.load(f)

def clean_text(text):

    '''
    Barebones text processing.
    '''
    
    cleaned_text = re.sub(r'<[^>]+>', '', text
                        ).replace('\xa0',' '
                        ).replace('\n',' '
                        ).replace('\r',''
                        ).replace('&amp;','&'
                        ).replace('  ',' '
                        ).replace('\u2019', "'"
                        ).replace('\u2013', "-"
                        ).replace('&#039;',"'"
                        ).replace('\u201c',"'"
                        ).replace('\u201d',"'"
                        ).replace('"',"'"
                        ).strip()
    return cleaned_text

def s(number):

    '''
    Function for pluralizing counts.
    '''

    if number == 1:
        return ''
    else:
        return 's'

def extract_value(json, location, sub_location=None, rule=None):

    '''
    W.I.P. function for extracting information from json given locations and rules.
    '''

    try:
        value = json[location[0]]
        if not value:
            return None       
        if len(location) > 1:
            for idx, i in enumerate(location[1:]):
                if idx != len(location) - 1: # if not last key in list
                    value = value[i] # go one layer deeper
                    if not value:
                        return None
        
        if rule in ['list','list_genres']:
            if sub_location:
                value_list = []
                for v in value:
                    value_in_list = v[sub_location[0]]
                    if len(sub_location) > 1:
                        for idx, i in enumerate(sub_location[1:]):
                            if idx != len(sub_location) - 1: # if not last key in list
                                value_in_list = value_in_list[i] # go one layer deeper
                    value_list.append(value_in_list)   
            else:
                if isinstance(value, list):
                    value_list = value
                elif isinstance(value, str):
                    value_list = [value.title()]
                else:
                    value_list = [value]

            if len(value_list) > 0:
                if rule == 'list':
                    value = ', '.join(value_list)
                else:
                    value = value_list
            else:
                value = None

        if rule == 'shorten':
            if isinstance(value, str):
                if len(value) > 44:
                    value = value[:41] + '...'

        if rule == 'listeners':
            if value:
                value = f"{str(value)} listener{s(value)}"
            
        if isinstance(value, str):
            return clean_text(value)
        else:
            return value
    
    except KeyError:
        return None

class Stream:

    '''
    Class to store Stream information containing functions to process now-playing data
    from each station and convert it into a dict to be served at /info.
    '''

    def __init__(self, from_dict=None, name=None, logo=None, location=None, info_link=None, stream_link=None, main_link=None, status=None, show_logo=None, now_playing=None, about=None, support_link=None, insta_link=None, bandcamp_link=None, soundcloud_link=None, hidden=False, genres=None, tuner_only=False, category=None, song_basis=False, cri_id=None):
        # station info 
        self.name = name
        self.cri_id = cri_id or cri.get(name)
        self.logo = logo
        self.location = location
        self.info_link = info_link
        self.stream_link = stream_link
        self.main_link = main_link
        self.about = about
        self.support_link = support_link
        self.insta_link = insta_link
        self.bandcamp_link = bandcamp_link
        self.soundcloud_link = soundcloud_link
        self.hidden = hidden
        self.genres = genres
        self.tuner_only = tuner_only
        self.category = category
        self.song_basis = song_basis

        # show info
        self.status = status
        self.now_playing_artist = None
        self.now_playing = now_playing
        self.now_playing_subtitle = None
        self.now_playing_description = None
        self.now_playing_description_long = None
        self.additional_info = None
        self.show_logo = show_logo
        self.last_updated = None
        self.one_liner = None
        self.listeners = None

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
            self.one_liner = self.one_liner
            self.support_link = from_dict.get('supportLink')
            self.hidden = from_dict.get('hidden')
            self.listeners = from_dict.get('listeners')
            self.genres = from_dict.get('genres')
            self.tuner_only = from_dict.get('tunerOnly')
            self.category = from_dict.get('category')
            self.song_basis = from_dict.get('songBasis')
            self.cri_id = from_dict.get('criId')

    def to_dict(self):

        '''
        Returns Stream properties as a dict to be compiled and publicized at the /info endpoint.
        '''

        return {
            "name": self.name,
            "logo": self.logo,
            "about": self.about,
            "location": self.location,
            "status": self.status,
            "songBasis": self.song_basis,
            "criId":self.cri_id,

            "infoLink": self.info_link,
            "streamLink": self.stream_link,
            "mainLink": self.main_link,
            "showLogo": self.show_logo,
            "supportLink": self.support_link,

            "nowPlaying": self.now_playing,
            "nowPlayingSubtitle": self.now_playing_subtitle,
            "nowPlayingArtist": self.now_playing_artist,
            "nowPlayingDescription": self.now_playing_description,
            "nowPlayingDescriptionLong": self.now_playing_description_long,
            "nowPlayingAdditionalInfo": self.additional_info,

            "bandcampLink": self.bandcamp_link,
            "soundcloudLink": self.soundcloud_link,
            "instaLink": self.insta_link,

            "lastUpdated": self.last_updated,

            "oneLiner":self.one_liner,
            "hidden":self.hidden,
            "listeners":self.listeners,
            "genres":self.genres,
            "tunerOnly":self.tuner_only,
            'category':self.category
        }
    
    def update(self):

        '''
        The main function for fetching updated now-playing data for each station. 
        Each "if" statement contains unique logic for gathering and processing station metadata.
        '''

        if "internetradioprotocol.org" not in self.logo:
            self.logo = "https://internetradioprotocol.org/" + self.logo

        if self.name == 'HydeFM':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.genres = None
            self.now_playing = extract_value(info, ['showTitle'])
            self.status = "Live" if self.now_playing else "Offline"
            self.stream_link = 'https://stream.hydefm.com/hls/0/stream.m3u8'

            if self.status == 'Offline':
                offline_info = requests.get('https://hydefm.com/wp-json/hydefm/v1/offline-now').json()
                try:
                    time_into = offline_info['offset']
                    shows = offline_info['order']
                    show_index = offline_info['index']
                    show = shows[show_index]
                    self.stream_link = show['audio'] + f'#t={time_into}'
                    self.now_playing = 'Rerun: ' + show['title']
                    self.status = 'Re-Run'

                    url = 'https://hydefm.com/archive' + show['path']
                    soup = BeautifulSoup(requests.get(url, timeout=TIMEOUT).text, 'html.parser')

                    '''
                    widget_containers = soup.find_all(attrs={'class':'elementor-widget-container'})
                    for i in widget_containers:
                        if i.find_all(attrs={'rel':'tag'}):
                            tags = i.find_all('a')
                            genres = []
                            for tag in tags:
                                genres.append(tag.text)
                            self.genres = genres
                            break
                    '''

                except Exception as e:
                    print(e)
                
        if self.name in ['SutroFM','Lower Grand Radio','Vestiges']:
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['name'])
            self.additional_info = None 
            self.listeners = extract_value(info, ['listeners'], rule='listeners')
            self.show_logo = extract_value(info, ['image'])

            if self.show_logo:
                img = Image.open(BytesIO(requests.get(self.show_logo, timeout=3).content)).convert("RGB")
                if (img.getpixel((0,0)) == (255, 255, 255)) and (img.getpixel((100,100)) == (255, 255, 255)):
                    self.show_logo = None
            self.now_playing_description_long = extract_value(info, ['description'])
            self.now_playing_description = extract_value(info, ['description'], rule='shorten')
            self.status = "Live" if info['online'] == True else "Offline"

        elif 'NTS' in self.name and self.category != 'Mixtape':
            info = requests.get(self.info_link + '/?cacheBust=' + str(random.randint(0,1000000)), timeout=TIMEOUT).json()
            result_idx = 0 if self.name == 'NTS 1' else 1
            now = info['results'][result_idx]['now']
            self.now_playing = extract_value(now, ['broadcast_title'])  # show name like "In Focus: Timbaland"
            self.location = extract_value(now, ['embeds','details','location_long']) or 'London' # location like "New York"
            self.show_logo = extract_value(now, ['embeds','details','media','background_large'])
            self.now_playing_description_long =  extract_value(now, ['embeds','details','description']) # full description
            self.now_playing_description =  extract_value(now, ['embeds','details','description'], rule='shorten') # abridged description
            self.additional_info =  extract_value(now, ['embeds', 'details','moods'], sub_location=['value'], rule='list')
            self.genres = extract_value(now, ['embeds', 'details','genres'], sub_location=['value'], rule='list_genres')
            self.status = 'Live'

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
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            for program in info:
                if program.get('startTime'):
                    if datetime.fromisoformat(program['startTime']) < now:
                        self.now_playing = program['eventTitleMeta']['eventName'] # show name like "Dying Songs"
                        self.status = 'Live'
                        self.now_playing_artist = program['eventTitleMeta']['artist'] if program['eventTitleMeta']['artist'] else "Dublab" # artist name if provided lile "Jimmy Tamborello"
                        try:
                            # https://www.google.com/url?q=https://dublab-api-1.s3.amazonaws.com/uploads/2019/06/DUBLAB-The-Sounds-of-Now-TITLE-1.jpg&sa=D&source=calendar&ust=1782000699600490&usg=AOvVaw3I11-4vMAy6SHg0irq8Sjc
                            self.show_logo = program['attachments'] 
                            if 'www.google.com/url?q=' in self.show_logo:
                                self.show_logo = self.show_logo.split('?q=')[1].split('&')[0]
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
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.additional_info = None
            self.now_playing_artist = None
            self.genres = ['Student']
            self.status = 'Live'

            if info['metadata']:
                self.now_playing = extract_value(info,['metadata','playlist_title'])
                self.now_playing_artist = extract_value(info,['metadata','dj'])
                self.now_playing_subtitle = extract_value(info,['metadata','release_title'])
            else:
                self.now_playing = extract_value(info,['playlist','title'])

            self.show_logo = extract_value(info,['playlist','image'])
            if requests.get(self.show_logo, timeout=3).status_code != 200:
                self.show_logo = None
             
            if info['metadata']['artist_name'] and self.additional_info:
                self.additional_info += ' by ' + extract_value(info,['metadata','artist_name'])
            if info['metadata']['release_year'] and self.additional_info:
                self.additional_info += " (" + str(extract_value(info,['metadata','release_year'])) + ")"

            self.now_playing_description_long = extract_value(info,['playlist','description'])
            self.now_playing_description = extract_value(info,['playlist','description'], rule='shorten')

        elif self.name == 'Voices Radio': 
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Live'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # just artist name if possible like "Willow"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[0]) # just show name if posible like "Wispy"
                except:
                    self.now_playing_artist = None
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ','').replace('.mp3','')) # full title like "Wispy w/ Willow"

                if self.now_playing == 'ARCHIVE':
                    self.status = 'Re-Run'

        elif self.name == 'Kiosk Radio': 
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if not info['shows']['current']['name']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
                self.now_playing_subtitle = None
            else:
                self.now_playing  = extract_value(info, ['shows','current','name']) # broadcast name like "Staff Picks" or "Piffy (live)"
                self.status = 'Live'
                self.now_playing_subtitle = extract_value(info, ['tracks','current','name']) # episode title "Delodio"

                type = extract_value(info, ['tracks','current','type'])
                if type == 'livestream':
                    self.stream_link = 'https://origin.streamnerd.nl/kioskradio/kioskradio/playlist.m3u8'
                else:
                    self.stream_link = 'https://kioskradiobxl.out.airtime.pro/kioskradiobxl_b'


        elif self.name == 'Do!!You!!! World': 
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Live'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # artist name like "Charlemagne Eagle"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split('w/')[0]) # show name like "The Do!You!!! Breakfast Show"
                except:
                    self.now_playing_artist = None
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','')) # show name like "The Do!You!!! Breakfast Show w/ Charlemagne Eagle"

        elif self.name == 'Radio Raheem': 
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Live'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

        elif self.name == 'Stegi Radio': 
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Live'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

        elif self.name == 'Radio Quantica':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            live_link = 'https://owncast.radioquantica.com/api/status'
            live_info = requests.get(live_link, timeout=TIMEOUT).json()
            if live_info['online'] == True:
                self.status = 'Live'
                self.stream_link = 'https://lon1.digitaloceanspaces.com/radio-quantica-owncast/hls/0/stream.m3u8'
            else:
                self.status = 'Re-Run'
                self.stream_link = 'https://libretime.radioquantica.com/main.mp3'

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
            response = requests.post(self.info_link, data=payload, headers=headers, timeout=TIMEOUT).json()
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

            response = requests.get(url, params=params, timeout=TIMEOUT)
            data = response.json()
            self.additional_info = None 
            self.now_playing = 'Re-Run'
            self.now_playing_description = None
            self.genres = None
            self.now_playing_subtitle = None
            self.now_playing_description_long = None   
            self.status = 'Re-Run'

            for event in data.get('items', []):
                end_time_str = event['end']['dateTime']
                end_time = datetime.fromisoformat(end_time_str)

                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str)
                now_utc = datetime.now(timezone.utc)            

                if end_time > now_utc > start_time:
                    self.now_playing = event['summary']
                    self.status = 'Live'
                    try:
                        description_lines = event['description'].replace('&nbsp;','<br>').replace('\n','<br>').split('<br>')
                        self.now_playing_description_long = clean_text(description_lines[0]) # long desc 
                        self.now_playing_description = self.now_playing_description_long[:44] + '...'# short desc like "A late night special with Kem Kem playing from the heart ..."
                        last_line = clean_text(description_lines[-1])  # genre list like "World, Jazz, Afrobeats, Electronic"
                        if last_line:
                            if '.' not in last_line:
                                self.genres = extract_value(last_line, rule='list_genres')
                        
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
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['tracks','current','metadata','track_title'])
            self.status = 'Live'
            if not self.now_playing:
                self.now_playing = extract_value(info, ['shows','current','name'])
            self.now_playing_artist = extract_value(info, ['tracks','current','metadata','artist_name'])
            if not self.now_playing:
                self.status = 'Offline'
            
        elif self.name == 'KQED':
            today = date.today().isoformat()
            epoch_time = int(time.time())
            info = requests.get(self.info_link + today + '?cachebust=' + str(random.randint(0,10000)), timeout=TIMEOUT).json()
            programs = info['data']['attributes']['schedule']

            for program in programs:
                if int(program['startTime']) < epoch_time:
                    self.now_playing = program['programTitle'] # broader series title like "Climate One"
                    self.now_playing_subtitle = program['episodeTitle'] # specific episode title like "Gina McCarthy on Cutting Everything but Emissions"
                    self.additional_info = program['programSource'] # sometimes NPR or BBC
                    self.status = 'Live'
                    try:
                        self.now_playing_description = clean_text(program['programDescription'])[:44] + '...' # series description like "The Trump administration has been dismantlin..."
                        self.now_playing_description_long = clean_text(program['programDescription']) # full series description
                    except:
                        self.now_playing_description = None
                        self.now_playing_description_long = None
                        pass

        elif self.name == 'We Are Various':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['is_online'] == True else 'Offline'
            self.additional_info = None
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['title'] # simple show title

        elif self.name == 'KWSX':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['is_online'] == True else 'Offline'
            self.additional_info = None 
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['text'] # simple show title

        elif self.name == 'KJazz':
            webpage = requests.get(self.main_link, timeout=TIMEOUT).text
            soup = BeautifulSoup(webpage, 'html.parser')
            self.now_playing = soup.find_all("a", "noDec")[1].get_text() # host name
            self.status = 'Live'
            self.now_playing_artist = None

        elif self.name == "Particle FM":
            info = requests.get(self.info_link, timeout=TIMEOUT).json()[0]
            self.additional_info = None 
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            rerun = ' (R)' if not info['live']['is_live'] else ''
            self.status = 'Live'
            self.now_playing = info['now_playing']['song']['title'] + rerun

        elif self.name == 'KEXP':
            now_utc = datetime.now(timezone.utc)
            info = requests.get(self.info_link, timeout=TIMEOUT)
            song = info.json()['results'][0]
            show_uri = song['show_uri']
            show = requests.get(show_uri).json()
            self.status = 'Live'

            self.now_playing_artist = ', '.join(show['host_names']) # concatenation of host names
            self.now_playing = show['program_name'] # concatenation of host names show name
            self.additional_info = None
            self.genres = show['program_tags'].split(',')
            self.show_logo = None#show['program_image_uri'] # show logo if provided
            self.now_playing_subtitle = None
            if song['play_type'] == 'trackplay':
                self.now_playing_subtitle = f"{song['song']} by {song['artist']}" # last played song and artist
        
        elif self.name == 'Clyde Built Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            try:
                self.now_playing = info['shows']['current']['name'] # just song name
                self.status = 'Live'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'SF 10-33':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = info['songs'][0]['title']
            self.now_playing_artist = info['songs'][0]['artist']
            self.now_playing_subtitle = info['songs'][0]['album']
        
        elif self.name == 'SomaFM Live':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
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

            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            now_utc = datetime.now(timezone.utc)
            shows = info['channels']
            episodes = [i for i in info['episodes'] if i['channel'][0]['slug'] == name_to_slug_dict[self.name]]
            
            self.now_playing = 'Playlist'
            for i in episodes:
                episode_time = datetime.fromisoformat(i['episodeTime']) 
                episode_date = datetime.fromisoformat(i['episodeDate']) + timedelta(minutes=60)

                episode_length = i.get('episodeLength') or 120
                episode_end = episode_time + timedelta(minutes=episode_length)

                if (episode_time <= now_utc <= episode_end) & (episode_date.date() == now_utc.date()):
                    self.now_playing = i['title']
                    self.now_playing_subtitle = i['subtitle']
                    self.status = 'Live'
                    self.genres = None
                    self.additional_info = None

                    try:
                        self.genres = extract_value(i, ['parentShow',0,'genreTag'],['title'],rule='list_genres')
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
            try:
                info = requests.get(self.info_link, timeout=TIMEOUT).json()
                self.now_playing = info['tracks']['current']['metadata']['track_title']
                self.status = "Live"
                try:
                    url = 'https://radio.syg.ma/episodes/' + info['tracks']['current']['metadata']['info_url']
                    soup = BeautifulSoup(requests.get(url, timeout=TIMEOUT).text, "html.parser")
                    self.show_logo = soup.find("meta", property="og:image")['content']
                except Exception as e:
                    print(e)
                    self.show_logo = None

            except:
                self.now_playing = None
                self.status = "Offline"
                self.show_logo = None

        elif self.name == 'LYL Radio':
            try:
                info = requests.post(self.info_link,data={"variables":{},"query":"{\n  onair {\n    title\n    hls\n    __typename\n  }\n}\n"}, timeout=TIMEOUT)
                self.now_playing = info.json()['data']['onair']['title']
                if "WE'LL BE BACK" not in self.now_playing:
                    self.status = 'Live'
                else:
                    self.status = 'Offline'
            except:
                self.now_playing = None
                self.status = 'Offline'
        
        elif self.name == 'Skylab Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            self.now_playing = None
            self.additional_info = None
            self.show_logo = None
            self.status = "Offline"

            try:
                self.now_playing = info['currentShow'][0]['name']
                self.now_playing_subtitle = info['current']['track_title'] + ' by '+ info['current']['artist_name']
                self.status = "Live"
            except:
                try:
                    self.now_playing = info['currentShow'][0]['name']
                    self.status = "Live"
                except:
                    pass

            try:
                self.show_logo = info['metadata']['artwork_url']
            except:
                self.show_logo = None
        
        elif self.name == 'BFF.fm':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = info['program']
            self.now_playing_artist = info['presenter']
            self.status = 'Live'
            try:
                self.now_playing_subtitle = info['title'] + ' by ' + info['artist']
            except:
                self.now_playing_subtitle = info['title']
            try:
                self.show_logo = None#info['program_image'].replace('\/','/')
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

            response = requests.get(url, params=params, timeout=TIMEOUT)
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
                    self.status = 'Live'
                    self.now_playing = event['summary']
        
        elif self.name == 'Radio Alhara':
            self.status = 'Live'
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = info['title']
            self.now_playing_artist = info['artist']
        
        elif self.name == 'Mutant Radio':
            self.status = 'Live'
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = info['title']

        elif self.name == 'n10.as':
            self.status = 'Live'
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = info['currentShow'][0]['name']
            self.additional_info = 'Next: ' + info['nextShow'][0]['name']

        elif self.name == 'Radio Banda Larga':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live'
            try:
                self.now_playing = extract_value(info, ['result','content','title'])
            except:
                self.now_playing = None
                self.status = 'Offline'
            
            try:
                if extract_value(info, ['result','metadata']) == 'Live':
                    self.status = 'Live'
                else:
                    self.status == 'Re-Run'
            except:
                self.status = 'Offline'

        elif self.name == 'Subtle Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            try:
                self.now_playing = info['shows']['current']['name']
                self.now_playing_description = info['shows']['current']['description']
                self.now_playing_subtitle = info['tracks']['current']['name'].lstrip(' - ').replace('.mp3','')
                self.status = 'Live'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == "Monotonic Radio":
            info = requests.get(self.info_link, timeout=TIMEOUT).json()

            self.status = "Offline"
            try:
                self.now_playing = info['now_playing']
                if info['source'] == 'live':
                    self.stream_link = 'http://monotonicradio.com:8000/stream.m3u'
                    self.status = "Live"
                else: 
                    self.stream_link = 'https://monotonicradio.com/stream'
                    self.status = "Re-Run"
            except:
                pass
            self.now_playing_description = info.get('video_description')
            self.genres = extract_value(info, ['genres'], rule='list_genres')
             
        elif self.name == 'HKCR':
            '''
            stream_url = self.stream_link
            tmp_file = tempfile.mktemp(suffix='.jpg')
            self.status = 'Live'
            
            subprocess.run([
                'ffmpeg', '-i', stream_url, '-frames:v', '1',
                '-vf', 'crop=in_w*0.45:in_h*0.038:in_w*0.037:in_h*0.035,eq=contrast=3.0,format=gray',
                tmp_file, '-hide_banner', '-y'
            ], capture_output=True, timeout=TIMEOUT)
            
            if os.path.exists(tmp_file):
                result = subprocess.run(['tesseract', tmp_file, 'stdout'],
                                    capture_output=True, text=True, timeout=TIMEOUT)
                os.remove(tmp_file)
                self.now_playing = result.stdout.strip().strip('-').strip("'").strip(':').strip('Live - ').strip('? - ')
            '''
            rn = datetime.now(timezone.utc)
            today = date.today().isoformat()
            tomorrow = date.today() + timedelta(days=1)
            self.now_playing = None
            self.show_logo = None
            self.status = 'Offline'

            url = self.info_link + f"/replay-slots/range?startDate={today}&endDate={tomorrow}"
            info = requests.get(url, timeout=TIMEOUT).json()
            for i in info['slots']:
                if (rn > datetime.fromisoformat(i['start'])) & (rn < datetime.fromisoformat(i['end'])):
                    self.now_playing = extract_value(i, ['replay', 'title'])
                    self.status = 'Re-Run'
                    show_id = i['show']
                    show_info = requests.get('https://cms.hkcr.live/shows/' + show_id, timeout=3).json()
                    self.show_logo = extract_value(show_info, ['picture','url'])

            if self.now_playing == None:
                url = self.info_link + f"/schedule/range?startDate={today}&endDate={tomorrow}"
                info = requests.get(url, timeout=TIMEOUT).json()
                for i in info:
                    start = i['date'] + 'T' + i['startTime'] + '+00:00'
                    if i['startTime'] > i['endTime']:
                        end = datetime.fromisoformat(i['date']  + 'T' + i['endTime'] + '+08:00')
                    else:
                        end = datetime.fromisoformat(i['date']  + 'T' + i['endTime'] + '+08:00') + timedelta(1)
                    if (rn > datetime.fromisoformat(start)) & (rn < end):
                        self.now_playing = extract_value(i, ['title'])
                        self.show_logo = extract_value(i, ['picture','url'])
                        self.status = 'Live'
            
            if self.show_logo:
                parts = urlsplit(self.show_logo)
                self.show_logo = urlunsplit(parts._replace(path=quote(parts.path)))

            
        elif self.name == 'CKUT':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.genres = ['Student']
            self.status = 'Live'
            self.now_playing = info['program']['title_html']
            self.now_playing_description_long = clean_text(info['program']['description_html'])
            if len(self.now_playing_description_long) > 44:
                self.now_playing_description = clean_text(info['program']['description_html'])[:44] + '...'
            else: 
                self.now_playing_description = clean_text(info['program']['description_html'])

        elif self.name == 'Shared Frequencies':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['current','metadata','track_title'])
            self.now_playing_artist = extract_value(info, ['current','metadata','artist_name'])
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Radio Nopal':
            self.now_playing = None
            calendar_id = self.info_link
            api_key = 'AIzaSyD7jIVZog7IC--y1RBCiLuUmxEDeBH9wDA'
            url = f'https://www.googleapis.com/calendar/v3/calendars/{calendar_id}/events'
            time_minus_1hr = (datetime.now(timezone.utc) - timedelta(hours=1)).replace(microsecond=0).isoformat()
            params = {
                'key': api_key,
                'maxResults': 3,
                'singleEvents': True,
                'orderBy': 'startTime',
                'timeMin': time_minus_1hr
            }

            response = requests.get(url, params=params, timeout=TIMEOUT)
            data = response.json()

            for event in data.get('items', []):
                end_time_str = event['end']['dateTime']
                end_time = datetime.fromisoformat(end_time_str)
                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str)
                now_utc = datetime.now(timezone.utc)

                if end_time > now_utc > start_time:
                    self.now_playing = event['summary']
                    if 'Archivo' in event.get('summary') or '':
                        self.stream_link = 'https://radio.mensajito.mx/nopalVentana'
                    else:
                        self.stream_link = 'https://radio.mensajito.mx/nopalA'
                
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Noods Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['result','content','title'])
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Radio Punctum':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['data','title'])
            self.now_playing_artist = extract_value(info, ['data','artists'], ['name'], rule='list')
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Radio 80000':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['currentShow',0,'name'])
            self.status = "Live" if self.now_playing else "Offline"
        
        elif self.name == 'stayfm':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['showQueued','title'])
            self.now_playing_artist = extract_value(info, ['showQueued','host'])
            if info['onair'] == 'archive' or info['onair'] == 'off':
                self.stream_link = info['streamArchive']
                self.status = 'Re-Run'
            else:
                self.stream_link = info['streamLive']
                self.status = 'Live'

        elif self.name == 'Oroko Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['result','metadata','title'])
            self.now_playing_artist = extract_value(info, ['result','metadata','artist'])
            self.show_logo = extract_value(info, ['result','metadata','artwork','512x512'])
            self.status = 'Live'

        elif self.name == 'Desire Path Radio':
            ch2_info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Offline'
            self.genres = None
            if ch2_info['online'] == True:
                info = ch2_info
                self.status = 'Live'
                self.genres = ['Talk']
            else:
                info = requests.get(self.info_link.replace('-channel-2',''), timeout=TIMEOUT).json()
                if info['online'] == True:
                    self.status = 'Live'
            
            self.stream_link = info['streamUrl']
            if self.status == 'Offline':
                self.now_playing = None
                self.now_playing_artist = None
                self.now_playing_description = None
                self.now_playing_description_long = None
                self.listeners = extract_value(info, ['listeners'])    
            else:            
                self.now_playing = extract_value(info, ['name'])
                self.now_playing_artist = extract_value(info, ['host'])
                self.now_playing_description = extract_value(info, ['description'], rule='shorten')
                self.now_playing_description_long = extract_value(info, ['description'])
                self.listeners = extract_value(info, ['listeners'])
        
        elif self.name == 'Veneno':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['current','metadata','track_title'])
            self.now_playing_artist = extract_value(info, ['current','metadata','artist_name'])
            self.genres = extract_value(info, ['current','metadata','genre'], rule='list_genres')
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Radio Relativa':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if extract_value(info, ['status']) == 'online' else 'Offline'
            self.now_playing = extract_value(info, ['current_track','title']).replace('Live Now - ', '')

        elif self.name == 'Radio Vilnius':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = None
            self.now_playing_artist = None
            self.status = 'Offline'
            self.listeners = None
                
            for i in info['allStats']:
                if 'server_name' in i.keys():
                    if i['server_name'] == 'Radio Vilnius':
                        self.now_playing = extract_value(i, ['title'])
                        self.now_playing_artist = extract_value(i, ['artist'])
                        if self.now_playing:
                            self.status = "Live"
                        self.listeners = extract_value(i, ['listener_peak'])

                        
        elif self.name == 'Rukh Radio':
            headers = {
                'Accept':'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15'
            }
            info = requests.get(self.info_link, headers=headers, timeout=TIMEOUT + 10).text
            self.now_playing = info
            if 'Account Suspended' or 'Resource Limit Is Reached' in self.now_playing:
                self.now_playing = 'Rukh Playlist'
                self.status = 'Re-Run'
            else:
                self.status = "Live" if self.now_playing else "Offline"
    
        elif self.name == 'Pan African Space Station':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing_artist = extract_value(info, ['current','metadata','artist_name'])
            self.now_playing = extract_value(info, ['current','metadata','track_title']) or ''
            self.now_playing = self.now_playing.replace('.mp3','')
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Refuge Worldwide':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['status'] == 'online' else 'Offline'
            self.show_logo = extract_value(info, ['liveNow', 'artwork'])
            if self.show_logo:
                if 'default-image' in self.show_logo:
                    self.show_logo = None
            self.now_playing = extract_value(info, ['liveNow','title']).split(' - ')[0]
            try:
                self.now_playing_artist = extract_value(info, ['liveNow','title']).split(' - ')[1]
            except:
                self.now_playing_artist = None
            
        elif self.name == 'Cashmere Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['isLive']==True else 'Offline' if info['isActive']==False else 'Re-Run'
            self.now_playing = extract_value(info, ['name'])
            self.now_playing_description = extract_value(info, ['description'])

        elif self.name == 'Soho Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['currentShow', 0, 'name'])
            self.now_playing_description = extract_value(info, ['currentShow',0,'description'])
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'Worldwide FM':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['currentEvent','showName'])
            self.now_playing_artist = extract_value(info, ['currentEvent','artists'], rule='list')
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'KUSF':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['show','title'])
            self.now_playing_subtitle = extract_value(info, ['broadcast','title'])
            self.now_playing_description = extract_value(info, ['show','summary'])
            self.now_playing_artist = extract_value(info, ['show','users'], ['display_name'], rule='list')
            self.status = "Live" if self.now_playing else "Offline"

        elif self.name == 'program audio':
            resp = requests.get(self.info_link, timeout=TIMEOUT).text
            soup = BeautifulSoup(resp, features='html.parser')
            title = soup.find(attrs={'name':"description"})
            if title:
                self.status = "Live"
                full_title = title['content']
                if '|' in full_title:
                    self.now_playing = full_title.split('|')[0].strip()
                else:
                    self.now_playing = full_title
            else:
                self.status = "Offline"
                self.now_playing = "Offline"

        elif self.name == 'KALX':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.show_logo = None
            self.now_playing = extract_value(info, ['show','title'])
            self.now_playing_description = extract_value(info, ['show','users',0,'profile_text'])
            if self.now_playing_description:
                self.now_playing_description = self.now_playing_description.replace('<p>','').replace('</p>','')
            if extract_value(info,['broadcast','is_archived']) == True:
                self.status = 'Re-Run'
            else:
                self.status = 'Live'

            # self.show_logo = extract_value(info, ['show','image','url'])
            if self.show_logo:
                try:
                    response = requests.get(self.show_logo, timeout=TIMEOUT)
                    assert response.status_code == 200
                except:
                    self.show_logo = None

            try:
                url = "https://kalx.berkeley.edu/wp-content/plugins/kalx-spinitron/now-playing.php"
                response = requests.get(url, timeout=TIMEOUT).text
                soup = BeautifulSoup(response, features='html.parser')
                artist = soup.find_all(attrs={'class':"small-15 artist bold"})[1]
                artist = artist.getText().strip()
                song = soup.find(attrs={'class':"song"})
                song = song.getText().strip()
                self.now_playing_subtitle = song + ' by ' + artist
            except Exception as e:
                print(e)
                self.now_playing_subtitle = None
        
        elif self.name in ['WKCR','WCFM']:
            resp = requests.get(self.info_link).text.replace('\\"', '"').replace("'", '"')
            soup = BeautifulSoup(resp[resp.find('(')+2:-3], features='html.parser')

            artist = soup.find('span', class_='artist').get_text(strip=True)
            song = soup.find('span', class_='song').get_text(strip=True)

            show_link = soup.find('td', class_='spin-time').find('a').get('href')
            resp = requests.get(show_link, timeout=TIMEOUT).text
            show_soup = BeautifulSoup(resp, features='html.parser')
            try:
                show_name = show_soup.find('h3').find('a').get_text()
            except:
                show_name = show_soup.find('h3').get_text()
            self.now_playing = show_name
            self.now_playing_subtitle = f'{song} by {artist}'

        elif self.name == 'Datafruits FM':
            timeout = 3
            ws = create_connection(
                    self.info_link,
                    origin="https://datafruits.fm",
                    header=[
                        "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
                        "Pragma: no-cache",
                        "Cache-Control: no-cache",
                    ],
                    timeout=timeout,
                )

            try:
                ws.send(json.dumps(["1", "1", "metadata", "phx_join", {}]))
                received = False
                while received == False:
                    msg = json.loads(ws.recv())
                    if msg[3] == "canonical_metadata":
                        self.now_playing = msg[4]["message"]['title']
                        received = True
            finally:
                ws.close()

        elif self.name == 'ChuntFM':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if len(info) > 0:
                self.now_playing = extract_value(info, [0,'title'])
                self.status = 'Live' if info[0].get('restream') == False else 'Re-Run'
            else:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'Palanga Street':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            name = extract_value(info, ['shows','current','name'])
            if name:
                self.now_playing = name
                self.now_playing_description = extract_value(info, ['shows','current','description'])
                id = extract_value(info, ['shows','current','id'])
                self.show_logo = 'https://api.palanga.live/show-logo?id=' + str(id)
                try: 
                    resp = requests.get(self.show_logo, timeout=3).status_code
                    assert resp==200
                except:
                    self.show_logo = None
                self.status = 'Live' if extract_value(info, ['sources','livedj']) == 'on' else 'Re-Run'
            else:
                self.now_playing = None
                self.now_playing_description = None
                self.show_logo = None
                self.status = 'Offline'

        elif self.name == 'Dublin Digital Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if info['success'] == True:
                self.now_playing = extract_value(info, ['result','content','name'])
                if not self.now_playing:
                    self.now_playing = extract_value(info, ['result','content','title'])
                self.status = 'Re-Run' if extract_value(info, ['result','status']) == 'defaultPlaylist' else 'Live'

                resp = requests.get(self.main_link, timeout=TIMEOUT).text
                soup = BeautifulSoup(resp, features='html.parser')
                imgs = soup.find_all(attrs={'class':'w-full'})
                if imgs:
                    self.show_logo = imgs[0].get('src')
                    if self.show_logo:
                        self.show_logo = self.show_logo.replace('http:','https:')
                else:
                    self.show_logo = None

            else:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'IDA':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            data = info['data']['tallinn']
            self.show_logo = None
            if data:
                self.now_playing = extract_value(data, ['title'])
                self.status = 'Re-Run' if data['isRepeat'] == True else 'Live'
                self.show_logo = data['featuredImage']
                if isinstance(self.show_logo, dict):
                    self.show_logo = self.show_logo['formats']['large']['url']
            else:
                self.now_playing = None
                self.status = 'Offline'
                self.show_logo = None

        elif self.name == 'Tīrkultūra':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if info['data']:
                self.now_playing = extract_value(info, ['data','title'])
                self.status = 'Live'
            else:
                self.status = 'Offline'

        elif self.name == 'Seyðisfjörður Community Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if info['success']:
                self.now_playing = extract_value(info, ['result','metadata','title'])
                artist = extract_value(info, ['result','metadata','artist'])
                if artist:
                    self.now_playing = self.now_playing + ' by ' + artist
                self.status = 'Re-Run' if extract_value(info, ['result','content','media','type']) == 'playlist' else 'Live'
            else:
                self.now_playing = None
                self.status = 'Offline'
        
        elif self.name == 'Lahmacun':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['live']['is_live'] == True else 'Re-Run'
            self.now_playing = extract_value(info, ['now_playing','song','text'])
            self.show_logo = extract_value(info, ['now_playing','song','art'])
            self.listeners = extract_value(info, ['listeners','total'])
            if self.status == 'Live':
                self.now_playing = extract_value(info, ['live','streamer_name']) + ' ' + self.now_playing
        
        elif self.name == 'Gatekeeper Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['live']['is_live'] == True else 'Re-Run'
            self.now_playing = extract_value(info, ['now_playing','song','text'])
            self.listeners = extract_value(info, ['listeners','total'])
        
        elif self.name == '20ft Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            
            if info['success'] == True:
                self.now_playing = extract_value(info, ['result','content','title'])
                self.status = 'Re-Run' if extract_value(info, ['result','status']) == 'defaultPlaylist' else 'Live'
            else:
                self.now_playing = None
                self.status = 'Offline'

            if not self.now_playing:
                self.status = 'Offline'
            else:
                try:
                    stream_resp = requests.get(self.stream_link, stream=True, timeout=5)
                    assert stream_resp.status_code == 200
                    self.status = 'Live'
                except:
                    self.status = 'Offline'
                    self.now_playing = None

        elif self.name == 'Parea Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live'
            self.now_playing = extract_value(info, ['title'])

        elif self.name == 'Radio Dopo':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['current_track','title'])
            self.show_logo = extract_value(info, ['current_track','artwork_url_large'])
            self.status = 'Re-Run' if extract_value(info, ['source','type']) == 'automated' else 'Live'
            if info['status'] != 'online':
                self.now_playing = None
                self.status = 'Offline'
                self.show_logo = None

        elif self.name == 'Radio Sofa':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.status = 'Live' if info['live']['is_live'] == True else 'Re-Run'
            self.now_playing = extract_value(info, ['now_playing','song','title'])
            artist = extract_value(info, ['now_playing','song','artist'])
            if artist:
                self.now_playing = self.now_playing + ' by ' + artist
            self.listeners = extract_value(info, ['listeners','total'])            
            if self.status == 'Live':
                self.now_playing = extract_value(info, ['live','streamer_name']) + ' ' + self.now_playing
        
        elif self.name == 'Sphere Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['currentShow',0,'name'])
            if not self.now_playing:
                self.status = 'Offline'
            else:
                try:
                    stream_resp = requests.get(self.stream_link, stream=True, timeout=5)
                    assert stream_resp.status_code == 200
                    self.status = 'Live'
                except:
                    self.status = 'Offline'
                    self.now_playing = None

        elif self.name == 'Zabrij Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            if info['success'] == True:
                self.now_playing = extract_value(info, ['result','metadata','title'])
                artist = extract_value(info, ['result','metadata','artist'])
                if artist:
                    self.now_playing = self.now_playing + ' by ' + artist
                self.status = 'Re-Run' if extract_value(info, ['result','status']) == 'defaultPlaylist' else 'Live'
            else:
                self.now_playing = None
                self.status = 'Offline'    

        elif self.name == 'Zone EST Radio':
            self.status = 'Live'
            ws = create_connection(
                self.info_link,
                origin="https://radio.zest.radio",
                header=[
                    "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15",
                    "Pragma: no-cache",
                    "Cache-Control: no-cache",
                ],
                timeout=timeout,
            )

            try:
                ws.send(json.dumps({"subs": {"station:zest_radio": {"recover": True}}}))
                received = False
                while received == False:
                    raw = ws.recv()
                    if raw.strip() in ("", "{}"):     
                        continue
                    msg = json.loads(raw)

                    pub = msg.get("pub")
                    if pub is None:
                        pubs = (msg.get("connect", {})
                                .get("subs", {})
                                .get("station:zest_radio", {})
                                .get("publications", []))
                        pub = pubs[0] if pubs else None
                    if pub is None:
                        continue

                    self.now_playing = pub["data"]["np"]["now_playing"]["song"]["title"] + ' by ' + pub["data"]["np"]["now_playing"]["song"]["artist"]
                    self.status = 'Live' if pub['data']['np']['live']['is_live'] == True else 'Re-Run'
                    received = True
            finally:
                 ws.close()    

        elif self.name == 'Depa Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info,['currentTrack'])
            if self.now_playing:
                self.status = 'Live'
            else:
                self.status = 'Offline'

        elif self.name == 'Muito Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info,['tracks','current','name'])
            if self.now_playing:
                self.status = 'Live'
            else:
                self.now_playing = extract_value(info,['shows','current','name'])
                if self.now_playing:
                    self.status = 'Live'
                else:
                    self.status = 'Offline'

        elif self.name == 'East Village Radio':
            headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Priority": "u=0, i",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"
            }
            info = requests.get(self.info_link, timeout=TIMEOUT,headers=headers).text
            soup = BeautifulSoup(info, features='html.parser')
            self.now_playing = soup.find(attrs={'class':'hidden-xs'}).text.strip().replace('\t','').replace('\n',' ').replace('  ',' ').replace('(Current Track) ','')
            if self.now_playing:
                self.status = 'Live'
            else:
                self.status = 'Offline'

        elif self.name == 'KXLU':
            self.now_playing = None
            self.status = 'Offline'
            headers = {
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Priority": "u=0, i",
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15"
            }
            info = requests.get(self.info_link, timeout=TIMEOUT,headers=headers).text
            soup = BeautifulSoup(info, features='html.parser')
            self.now_playing = soup.find(attrs={'class':'show-title'}).text.replace('\n','').strip()
            images = soup.find_all(attrs={'class':'image'})
            if len(images) > 1:
                self.show_logo = images[1].find('img').get('src')
                if 'https://' not in self.show_logo:
                    self.show_logo = 'https://spinitron.com' + self.show_logo
            else:
                self.show_logo = None
            if self.now_playing:
                self.status = 'Live'

        elif self.name == 'Operator Radio':
            info = requests.get(self.info_link, timeout=TIMEOUT).json()
            self.now_playing = extract_value(info, ['stream1',0,'setName'])
            self.now_playing_description_long = extract_value(info, ['stream1',0,'body'])
            self.now_playing_description = extract_value(info, ['stream1',0,'body'], rule='shorten')
            self.show_logo = extract_value(info, ['stream1',0,'images',0,'image','cloudinaryURL'])
            self.genres = extract_value(info, ['stream1',0,'genres'], rule='list_genres',sub_location=['genre'])
            if self.now_playing:
                self.status = 'Live'
            else:
                self.status = 'Offline'

    def set_last_updated(self):
        self.last_updated = datetime.now(timezone.utc)

    def update_one_line(self):
        parts = [
            self.now_playing,
            self.now_playing_artist,
            self.now_playing_subtitle,
        ]
        return_string = " - ".join(p for p in parts if p).replace(' - - ',' - ').replace('\n',' ')

        self.one_liner = return_string

        rerun_strs = ['rotazione notte','night moves','night files','repeats','(r)', 're-run', 're-wav', 'restream', 'playlist','replays','stayfmix','picks from the archive','archivo','subtle selects','rerun']

        if self.status != 'Offline':
            #self.status = 'Live'
            if any(string in self.one_liner.lower() for string in rerun_strs):
                self.status = 'Re-Run'

            if self.status == 'Live':
                date1 = re.search("([0-9]{2}\/[0-9]{2}\/[0-9]{4})", self.one_liner)
                if date1:
                    date = datetime.strptime(date1.group(), "%d/%m/%Y").date()
                    print('DATE1',date)
                    if date < datetime.now().date():
                        self.status = 'Re-Run'
                else:
                    date2 = re.search("([0-9]{2}\.[0-9]{2}\.[0-9]{2})", self.one_liner)
                    if date2:
                        try:
                            date = datetime.strptime(date2.group(), "%m.%d.%y").date()
                        except:
                            date = datetime.strptime(date2.group(), "%d.%m.%y").date()
                        if date:   
                            print('DATE2',date)                   
                            if date < datetime.now().date():
                                self.status = 'Re-Run'

    def process_logos(self):
        logo_file = self.logo.replace('https://internetradioprotocol.org/','')

        tmp = {}
        logo = Image.open(logo_file).convert('RGB')

        logo_96 = logo.resize((96,  96)).convert('RGB')
        logo_60 = logo.resize((60,  60)).convert('RGB')
        logo_25 = logo.resize((25,  25)).convert('RGB')
        logo_176 = logo.resize((176, 176)).convert('RGB')      
        logo_216 = logo.resize((216, 216)).convert('RGB')       

        # save images to dict
        tmp['logo_96'] = logo_96
        tmp['logo_60']  = logo_60
        tmp['logo_25'] = logo_25
        tmp['logo_176'] = logo_176
        tmp['logo_216'] = logo_216

        # save images to lib
        for i in ['96','60','25','176','216']:
            entire_path = f'logos/{self.name.replace(' ','_')}_{i}.pkl'
            with open(entire_path, 'wb') as f:
                pickle.dump(tmp[f'logo_{i}'], f)


## define streams
streams = [
Stream(
        name = "Worldwide FM",
        logo = "https://internetradioprotocol.org/logos/wwfm.png",
        location = "London",
        info_link = "https://www.worldwidefm.net/api/live/current",
        stream_link = "https://worldwide-fm.radiocult.fm/stream",
        main_link = "https://www.worldwidefm.net",
        about = "Worldwide FM curates and champions underground music, stories and culture from around the world. We showcase diverse and emerging talent. We build connections between artists, listeners and music communities. Our mission is to support and encourage the development of music cultures that originate from local, independent and community-driven moments around the world. Our radio programming, content production and special projects explore and connect the evolving diversity of global creativity across music. Founded in 2016 by internationally renowned DJ and broadcaster Gilles Peterson, we’re an independent community of music lovers, creators and organisers in nearly every corner of the world.",
        support_link = "https://www.worldwidefm.net/membership",
        insta_link = "https://www.instagram.com/worldwide.fm"
),
Stream(
        name = "Soho Radio",
        logo = "https://internetradioprotocol.org/logos/soho.jpg",
        location = "Soho",
        info_link = "https://sohoradiomusic.doughunt.co.uk/api/live-info",
        stream_link = "https://sohoradiomusic.doughunt.co.uk:8010/320mp3",
        main_link = "https://sohoradio.com/",
        about = "From its grass-roots founding in 2014, Soho Radio has grown to be an influential voice and amplifier for music and culture, bringing together people from Soho, London, the UK and globally. We are an online radio station broadcasting 250+ shows a month live from Soho and from New York to the world.",
        support_link = "https://sohoradiolondon.store",
        insta_link = "https://www.instagram.com/sohoradio/"
),
Stream(
        name = "Cashmere Radio",
        logo = "https://internetradioprotocol.org/logos/cashmere.jpg",
        location = "Berlin",
        info_link = "https://cashmereradio.com/api/live/?stream=30046",
        stream_link = "https://cashmereradio.out.airtime.pro/cashmereradio_b",
        main_link = "https://cashmereradio.com/",
        about = "Cashmere Radio is a not-for-profit community experimental radio station which was originally based in Lichtenberg, Berlin for the first six years of its existence before recently moving to our new studio headquarters in Wedding. The ambition of the station is to preserve and further radio and broadcasting practices by playing with the plasticity and malleability of the medium.",
        support_link = "https://cashmereradio.bandcamp.com/",
        insta_link = "https://www.instagram.com/cashmere_radio/",
        bandcamp_link = "https://cashmereradio.bandcamp.com/",
        soundcloud_link = "https://www.mixcloud.com/CashmereRadio/"
),
Stream(
        name = "Refuge Worldwide",
        logo = "https://internetradioprotocol.org/logos/refuge.jpg",
        location = "Berlin",
        info_link = "https://refugeworldwide.com/api/schedule",
        stream_link = "https://streaming.radio.co/s3699c5e49/listen",
        main_link = "https://refugeworldwide.com/",
        about = "Refuge Worldwide is a radio station, educational platform and event series, operating in Berlin Neukölln. The project started - simply named Refuge - in 2015 as a fundraising initiative working in solidarity with grassroots and non-profit organisations. Among others, we have worked with a young women’s centre, refugee housing support associations, a music school for marginalised persons, social equity groups, homelessness agencies, and a shelter for women and young persons fleeing domestic violence.",
        support_link = "https://www.patreon.com/refugeworldwide",
        insta_link = "https://www.instagram.com/RefugeWorldwide/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Pan African Space Station",
        logo = "https://internetradioprotocol.org/logos/pass.png",
        location = "Cape Town",
        info_link = "https://pass.airtime.pro/api/live-info",
        stream_link = "https://pass.out.airtime.pro/pass_a",
        main_link = "https://panafricanspacestation.org.za/",
        about = "Founded by Chimurenga in 2008, the Pan African Space Station (PASS) is a periodic, pop-up live radio studio; a performance and exhibition space; a research platform and living archive, as well as an ongoing, internet based radio station. Copyright of all material broadcast and published is held by PASS and the individual artists and authors.",
        support_link = "mailto:info@chimurenga.co.za",
        insta_link = "https://www.instagram.com/chimurenga_sa/?hl=en",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "BFF.fm",
        logo = "https://internetradioprotocol.org/logos/bff.png",
        location = "San Francisco",
        info_link = "https://bff.fm/api/data/onair/now.json",
        stream_link = "https://stream.bff.fm/1/mp3.mp3",
        main_link = "https://bff.fm",
        about = "BFF.fm – Best Frequencies Forever is a community radio station, broadcasting online from the heart of San Francisco's Mission District.",
        support_link = "https://bff.fm/donate",
        insta_link = "https://www.instagram.com/bffdotfm",
        bandcamp_link = None,
        soundcloud_link = None,
        song_basis = True
),
Stream(
        name = "Bloop Radio",
        logo = "https://internetradioprotocol.org/logos/bloop.png",
        location = "London",
        info_link = "https://blooplondon.com/wp-admin/admin-ajax.php?action=radio_station_current_show",
        stream_link = "https://radio.canstream.co.uk:8058/live.mp3",
        main_link = "https://www.blooplondon.com",
        about = "Family Operated Online Underground Radio Station based in the heart of Central London. Specialising in Electronic Music that broadcasts nothing but exclusive shows from London based Residents & Guests DJs.",
        support_link = "https://blooplondonshop.com",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        hidden = True
),
Stream(
        name = "CKUT",
        logo = "https://internetradioprotocol.org/logos/ckut.jpeg",
        location = "Montreal",
        info_link = "https://ckut.ca/currentliveshows.php?c=1&json=1",
        stream_link = "https://delray.ckut.ca:8001/903fm-192-stereo",
        main_link = "https://ckut.ca",
        about = "CKUT is a non-profit, campus/community radio station based at McGill University in Montreal. CKUT provides alternative music, news and spoken word programming to the city of Montreal, surrounding areas, and around the world 24 hours a day, 365 days a year. Hear us at 90.3 MHz on the FM dial or listen online, where we also store archives of every show that hits the airwaves. CKUT has been on the FM airwaves since 1987, with roots going back to McGill's radio club, which was founded in 1921, and CFRM, a cable radio station that broadcast out of the basement of the Shatner Building on McGill campus.",
        support_link = "https://ckut.ca/civicrm/contribute/transact/?reset=1&id=10",
        insta_link = "https://instagram.com/ckutmusic/",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/radiockut",
        category='Student'
),
Stream(
        name = "Clyde Built Radio",
        logo = "https://internetradioprotocol.org/logos/clyde.png",
        location = "Glasgow",
        info_link = "https://clydebuiltradio.airtime.pro/api/live-info-v2?timezone=America/Los_Angeles",
        stream_link = "https://clydebuiltradio.out.airtime.pro/clydebuiltradio_a",
        main_link = "https://www.clydebuiltradio.com",
        about = "Clyde Built Radio is a non-profit community radio station highlighting Glasgow’s music, arts and culture communities to the rest of the world.",
        support_link = "https://www.clydebuiltradio.com/support",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        hidden = True
),
Stream(
        name = "Desire Path Radio",
        logo = "https://internetradioprotocol.org/logos/dpr.png",
        location = "New York",
        info_link = "https://api.evenings.co/v1/streams/desire-path-radio-channel-2/public",
        stream_link = "https://media.evenings.co/s/MLr0Mpj1B",
        main_link = "https://desirepathradio.com",
        about = "Desire Path Radio celebrates radio broadcast as an accessible tool for discourse, entertainment, and world-building. Radio is, and always has been, radical. Desire paths are unofficial routes created by repeated traffic. Reflecting the patterns of human nature and both individual and collective will, these routes reveal an alternate, if not improved, way to move through space and interact with the world around us. DIY forever.",
        support_link = "https://vmgkdp-0h.myshopify.com/",
        insta_link = "https://www.instagram.com/desirepath.radio/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Do!!You!!! World",
        logo = "https://internetradioprotocol.org/logos/doyou.png",
        location = "London",
        info_link = "https://doyouworld.airtime.pro/api/live-info-v2",
        stream_link = "https://doyouworld.out.airtime.pro/doyouworld_a",
        main_link = "https://doyou.world",
        about = "",
        support_link = "https://doyou.world/collections/memberships",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Dublab",
        logo = "https://internetradioprotocol.org/logos/dublab.png",
        location = "Los Angeles",
        info_link = "https://www.dublab.com/.netlify/functions/schedule?tz=America%2FLos_Angeles",
        stream_link = "https://dublab.out.airtime.pro/dublab_a",
        main_link = "https://dublab.com",
        about = "dublab is a Los Angeles-based, community-supported internet radio station and creative collective dedicated to the growth of positive music, arts, and culture.",
        support_link = "https://www.dublab.com/support/memberships",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Fault Radio",
        logo = "https://internetradioprotocol.org/logos/fault.png",
        location = "San Francisco",
        info_link = "c_ae5b8ddc2f204a590949fe5d0ebad0f03d13e4a31bd6c3d9c3f8e06140a0deb9@group.calendar.google.com",
        stream_link = "https://player.twitch.tv/?autoplay=1&channel=Faultradio",
        main_link = "https://www.faultradio.com",
        about = "Fault Radio is the ultimate advocate for our local community, acting as a dynamic bridge between the Bay Area’s thriving arts scene and the broader music world.",
        support_link = "https://www.faultradio.com/donate",
        insta_link = "https://www.instagram.com/its_fault_radio/",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/faultradio",
        hidden = True
),
Stream(
        name = "HKCR",
        logo = "https://internetradioprotocol.org/logos/hkcr.jpg",
        location = "Hong Kong",
        info_link = "https://cms.hkcr.live",
        stream_link = "https://stream-test.hkcr.live/hls/main.m3u8",
        main_link = "https://hkcr.live",
        about = "Founded in 2016, Hong Kong Community Radio (HKCR) is a community platform and independent radio station comprised of creators, musicians, artists and fans with aims to broadcast and support independent works as an open platform.",
        support_link = "https://www.patreon.com/hkcr",
        insta_link = "https://www.instagram.com/hkcronline/",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/hkcrlive"
),
Stream(
        name = "HydeFM",
        logo = "https://internetradioprotocol.org/logos/hydefm.png",
        location = "San Francisco",
        info_link = "https://hydefm.com/wp-json/hydefm/v1/stream-status",
        stream_link = "https://stream.hydefm.com/hls/0/stream.m3u8",
        main_link = "https://hydefm.com",
        about = "HydeFM is a community-based multi-genre online radio station broadcasting out of San Francisco, CA.",
        support_link = "https://www.every.org/hydefm?donationId=f8d1ff72-0f9a-4cfc-9055-f54389b66ca7&utm_campaign=receipts&utm_medium=email&utm_source=donation",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Internet Public Radio",
        logo = "https://internetradioprotocol.org/logos/internet.png",
        location = "Guadalajara",
        info_link = "https://stream-relay-geo.internetpublicradio.live/api-filtered.php?_=1771441745614",
        stream_link = "https://stream-relay-geo.internetpublicradio.live/stream/main",
        main_link = "https://www.internetpublicradio.live",
        about = "Internet Public Radio is an independent cultural platform and radio station curated by local and international DJs, musicians and visual artists.",
        support_link = "https://www.internetpublicradio.live/ipr-plus",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "KEXP",
        logo = "https://internetradioprotocol.org/logos/kexpsq.jpg",
        location = "Seattle",
        info_link = "https://api.kexp.org/v2/plays/?format=json&limit=1",
        stream_link = "https://kexp-mp3-128.streamguys1.com/kexp128.mp3",
        main_link = "https://www.kexp.org",
        about = "KEXP is an international community of music lovers and music makers, and a nonprofit organization fostering relationship and community building through broadcast, online, and in-person music experiences.",
        support_link = "https://www.kexp.org/donate/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        hidden= False
),
Stream(
        name = "KJazz",
        logo = "https://internetradioprotocol.org/logos/kjazz.webp",
        location = "Long Beach",
        info_link = "https://www.kkjz.org/",
        stream_link = "https://das-edge11-live365-dal03.cdnstream.com/a49833/playlist.m3u8",
        main_link = "https://www.kkjz.org",
        about = "KKJZ 88.1 FM (“KJazz”) is the #1 full-time mainstream jazz station in the United States and one of the top ranked public radio stations in the country.",
        support_link = "https://kkjz.secureallegiance.com/kkjz/WebModule/Donate.aspx?P=WEB2020&PAGETYPE=PLG&CHECK=RmCkD65dLKTtDFdmd%2bo4ruzWDeZ%2beA1M",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        genres = ['Jazz'],
        hidden=True
),
Stream(
        name = "KQED",
        logo = "https://internetradioprotocol.org/logos/kqed.png",
        location = "San Francisco",
        info_link = "https://media-api.kqed.org/radio-schedules/",
        stream_link = "https://streams.kqed.org/kqedradio?onsite=true",
        main_link = "https://www.kqed.org",
        about = "KQED serves the people of Northern California with a community-supported alternative to commercial media.",
        support_link = "https://donate.kqed.org/donatetoday",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        genres = ['Talk'],
        hidden=True
),
Stream(
        name = "KUSF",
        logo = "https://internetradioprotocol.org/logos/kusf.png",
        location = "San Francisco",
        info_link = "https://kusf.studio.creek.org/api/current?x=1&studioId=21",
        stream_link = "https://listen.kusf.org/stream",
        main_link = "http://www.kusf.org/",
        about = "KUSF is the University of San Francisco's online radio station. KUSF as an FM station was known both nationally and internationally for its innovative programming and approach to music. From 1963 until 2011, KUSF was a student-run broadcast station owned by the University of San Francisco. Following the frequency's sale, KUSF announced plans to become an online-only station.",
        support_link = "https://www.givecampus.com/campaigns/7449/donations/new?pdesignation=kusf",
        insta_link = "https://www.instagram.com/kusforg",
        bandcamp_link = "https://kusforg.bandcamp.com",
        soundcloud_link = None,
        genres = ['Student'],
        category='Student'
),
Stream(
        name = "KWSX",
        logo = "https://internetradioprotocol.org/logos/kwsx2.png",
        location = "World",
        info_link = "https://stream.kwsx.online/api/nowplaying/kwsx",
        stream_link = "https://radio.kwsx.online/assets/playlists/high/kwsx.m3u",
        main_link = "https://radio.kwsx.online",
        about = "KWSX is the bleeding-edge of digital online radio. Created by a like-minded collective of freaks, KWSX cares to give music the space it needs to breathe. Radiation from computer screens is boiling our eyes. Use your ears.",
        support_link = "https://ko-fi.com/kwsxradio",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        song_basis = True
),
Stream(
        name = "Kiosk Radio",
        logo = "https://internetradioprotocol.org/logos/kiosk.webp",
        location = "Brussels",
        info_link = "https://kioskradiobxl.airtime.pro/api/live-info-v2",
        stream_link = "https://kioskradiobxl.out.airtime.pro/kioskradiobxl_b",
        main_link = "https://kioskradio.com",
        about = "Kiosk Radio is an online community radio and streaming platform broadcasting 24/7 from a wooden kiosk in the heart of Brussels’ historic 'Parc Royal'. The radio was founded in 2017 and broadcasts a wide range of music genres, from jazz to experimental, from rock to electronic music.",
        support_link = "https://shop.kioskradio.com",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Kool FM",
        logo = "https://internetradioprotocol.org/logos/kool.jpg",
        location = "London",
        info_link = "https://www.rinse.fm/api/query/v1/schedule/",
        stream_link = "https://admin.stream.rinse.fm/proxy/kool/stream",
        main_link = "https://www.rinse.fm/channels/kool/",
        about = "Kool FM, also known as Kool London, is a former London pirate radio station that now broadcasts on DAB and online, playing jungle, drum and bass, and old skool. Kool is generally regarded as being instrumental in the development of the jungle music scene.",
        support_link = "https://www.rinse.fm/shop/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "LYL Radio",
        logo = "https://internetradioprotocol.org/logos/lyl.jpg",
        location = "Lyon",
        info_link = "https://api.lyl.live/graphql",
        stream_link = "https://radio.lyl.live/hls/live.m3u8",
        main_link = "https://lyl.live",
        about = "Broadcasting live from Unité Centrale in Lyon, La Tour Orion in Paris, Brasserie Atlas in Brussels and Les Ateliers de la Ville in Marseille.",
        support_link = "https://www.paypal.com/donate/?cmd=_s-xclick&hosted_button_id=C37FVDHHSZCA6",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Lower Grand Radio",
        logo = "https://internetradioprotocol.org/logos/lgrnew.png",
        location = "Oakland",
        info_link = "https://api.evenings.co/v1/streams/lower-grand-radio/public",
        stream_link = "https://media.evenings.co/s/g1b9EBY39",
        main_link = "https://www.lowergrandradio.com",
        about = "If you would like to do a show, please contact us at lowergrandshows@gmail.com All ideas are welcome. Please include any links or information about a type of show you are thinking. Please be specific!",
        support_link = "https://www.paypal.com/donate/?cmd=_s-xclick&hosted_button_id=7QPWGHQ5QLXWC&source=url&ssrt=1752175580020",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Monotonic Radio",
        logo = "https://internetradioprotocol.org/logos/mtr.jpg",
        location = "New York",
        info_link = "https://monotonicradio.com/info",
        stream_link = "https://monotonicradio.com/stream",
        main_link = "https://monotonicradio.com",
        about = "Above the bar underground music.",
        support_link = "https://venmo.com/?txn=pay&audience=public&recipients=miles-barrow-1&note=Support%20Monotonic%20Radio",
        insta_link = "https://www.instagram.com/monotonicradio/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Mutant Radio",
        logo = "https://internetradioprotocol.org/logos/mutant.jpg",
        location = "Tbilisi",
        info_link = "https://api.radioking.io/widget/radio/mutant-radio/track/current",
        stream_link = "https://listen.radioking.com/radio/282820/stream/328621",
        main_link = "https://www.mutantradio.net",
        about = "Mutant Radio is a media platform that focuses on various directions: mixes, interviews, educational shows, live performances and discusssion broadcasts that are either live-streamed or filmed and streamed later on. It gathers various artists, DJs, and interesting personalities that have an opportunity to focus on the subject of their preference and their interest. What is unique about Mutant Radio is that it is mobile. The physical station is a fully-equipped caravan-wagon that is based in Tbilisi yet also streams from other regions and special locations around Georgia. Apart from the live streams, Mutant Radio also has an open-air cafe, where like-minded people have an opportunity to enjoy quality music and a friendly vibe.",
        support_link = "https://mutantradio.bandcamp.com/album/mutant-fundraising-compilation",
        insta_link = "https://www.instagram.com/mutantradiotbilisi/",
        bandcamp_link = "https://mutantradio.bandcamp.com",
        soundcloud_link = None
),
Stream(
        name = "NTS 1",
        logo = "https://internetradioprotocol.org/logos/nts1.png",
        location = "London",
        info_link = "https://www.nts.live/api/v2/live",
        stream_link = "https://stream-relay-geo.ntslive.net/stream",
        main_link = "https://nts.live",
        about = "NTS provides curious minds with a home for music discovery. Built by music lovers, for music lovers.",
        support_link = "https://www.nts.live/supporters",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "NTS 2",
        logo = "https://internetradioprotocol.org/logos/nts2.png",
        location = "Chicago",
        info_link = "https://www.nts.live/api/v2/live",
        stream_link = "https://stream-relay-geo.ntslive.net/stream2",
        main_link = "https://nts.live",
        about = "NTS provides curious minds with a home for music discovery. Built by music lovers, for music lovers.",
        support_link = "https://www.nts.live/supporters",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Noods Radio",
        logo = "https://internetradioprotocol.org/logos/noods.webp",
        location = "Bristol",
        info_link = "https://api.radiocult.fm/api/station/noods-radio/schedule/live",
        stream_link = "https://noods-radio.radiocult.fm/stream?_ic2=1764380384069",
        main_link = "https://noodsradio.com",
        about = "Born from Sunday morning sessions in 2015, Noods Radio began as a means to share music and bring people together. Since then Noods has become home to an array of misfits, collectors and selectors from around the globe. Tune in with open ears. No playlists, no ads, just the people.",
        support_link = "https://noodsradio.com/luvers",
        insta_link = "https://www.instagram.com/noodsradio/",
        bandcamp_link = "https://dummyhand.bandcamp.com",
        soundcloud_link = "https://www.mixcloud.com/NoodsRadio/"
),
Stream(
        name = "Oroko Radio",
        logo = "https://internetradioprotocol.org/logos/oroko.png",
        location = "Accra",
        info_link = "https://api.radiocult.fm/api/station/Oroko%20Radio/schedule/live",
        stream_link = "https://oroko-radio.radiocult.fm/stream",
        main_link = "https://oroko.live",
        about = "Oroko is a not-for-profit independent internet radio station based in Accra, Ghana. We aim to connect, inspire and empower through conversation, collaboration and community.",
        support_link = "https://oroko.live/support",
        insta_link = "https://www.instagram.com/orokoradio/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Particle FM",
        logo = "https://internetradioprotocol.org/logos/particle.jpg",
        location = "San Diego",
        info_link = "https://azuracast.particle.fm/api/nowplaying",
        stream_link = "https://azuracast.particle.fm/radio/8000/radio.mp3",
        main_link = "https://www.particle.fm",
        about = "Particle FM is a DIY community internet radio station based in San Diego. We are an intersection of different cultures, identities, and music styles focused on building a platform for underrepresented artists to share their wildest tastes in music.",
        support_link = "https://www.paypal.com/donate?token=LCf1aVOt7zZUOu_RvVLMHCt-AMaaNIkIk9kLxzPV5Mn4tlTfXYMo2oKH2qZTVdIpThcTb02HlSPuhItU",
        insta_link = "https://www.instagram.com/particlefm",
        bandcamp_link = "https://particlefm.bandcamp.com",
        soundcloud_link = None
),
Stream(
        name = "Radio 80000",
        logo = "https://internetradioprotocol.org/logos/80000.jpg",
        location = "Munich",
        info_link = "https://radio80k.airtime.pro/api/live-info",
        stream_link = "https://radio80k.out.airtime.pro/radio80k_a",
        main_link = "https://www.radio80k.de/",
        about = "Radio 80000 is a non-commercial community radio, streaming live every day from 8am till midnight from ZIRKA in the north of Munich. Founded in 2015, it has evolved to a platform promoting collaboration and cultural expression through music, dialogue and events throughout Germany. DJs, musicians, producers, journalists and music lovers present an individual idea of radio that goes beyond algorithms and commercial playlists. By highlighting local scenes and welcoming guests from around the world, we aim to create a community of like-minded individuals. The studio serves as a real life meeting point for everyone to listen and hang out.",
        support_link = "https://www.paypal.com/paypalme/support80000",
        insta_link = "https://www.instagram.com/radio80000/",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/radio80000",
        hidden = False
),
Stream(
        name = "Radio Alhara",
        logo = "https://internetradioprotocol.org/logos/alhara.png",
        location = "Palestine",
        info_link = "https://proxy.radiojar.com/api/stations/78cxy6wkxtzuv/now_playing/",
        stream_link = "https://stream.radiojar.com/78cxy6wkxtzuv",
        main_link = "https://www.radioalhara.net",
        about = "Palestine community radio.",
        support_link = "https://www.paypal.com/GB/fundraiser/charity/4920746",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Radio Banda Larga",
        logo = "https://internetradioprotocol.org/logos/rbl.png",
        location = "Turin",
        info_link = "https://api.radiocult.fm/api/station/rblmedia-a4a44e62/schedule/live",
        stream_link = "https://rblmedia-a4a44e62.radiocult.fm/stream",
        main_link = "https://www.rbl.media",
        about = "Radio is our primary medium, our ears our favourite tool. Other locations around the world.",
        support_link = "https://www.patreon.com/rblmedia",
        insta_link = "https://www.instagram.com/rbltorino/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Radio Nopal",
        logo = "https://internetradioprotocol.org/logos/radionopal.png",
        location = "CDMX",
        info_link = "hg6kmcb0vtdegapdfgjbi9rav0@group.calendar.google.com",
        stream_link = "https://radio.mensajito.mx/nopalA",
        main_link = "https://www.radionopal.com",
        about = "Radio Nopal is a collective, independent, and self-managed internet radio station based in Mexico City, powered by Mensajito.mx (a technology we created to broadcast, host, and distribute live radio and podcasts using free technology and open-source software). It is a network for the production, exploration, and circulation of alternative content covering artistic, cultural, and political topics with an intention to disseminate and make visible the invisible in a heterodox manner and through constant reinvention. Radio Nopal is, above all, a space for resistance and a platform for convergence that allows us to build a diverse community while empowering the creativity of the people who participate in it.",
        support_link = "https://www.patreon.com/cw/nopalradio",
        insta_link = "https://www.instagram.com/radionopal/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Radio Punctum",
        logo = "https://internetradioprotocol.org/logos/punctum.jpg",
        location = "Prague",
        info_link = "https://radiopunctum.cz/api/radio/programme/playingnow/",
        stream_link = "https://radiopunctum.cz:8001/radio",
        main_link = "https://radiopunctum.cz",
        about = "Founded in 2015, Radio Punctum is a DIY listener supported, advertising free radio platform based in Prague, Czechia. We support our network of local and non-local music enthusiasts, DJs, talk show hosts, and live musicians with a radio platform that celebrates and reflects their diversity, both online and in person at Tendance Listening Bar. All shows are archived on our website.",
        support_link = "https://buymeacoffee.com/radiopunctum",
        insta_link = "https://www.instagram.com/radio_punctum/",
        bandcamp_link = "https://punctumtapes.bandcamp.com",
        soundcloud_link = "https://soundcloud.com/radiopunctum",
        hidden = True
),
Stream(
        name = "Radio Quantica",
        logo = "https://internetradioprotocol.org/logos/quantica.jpeg",
        location = "Lisbon",
        info_link = "https://api.radioquantica.com/api/live-info",
        stream_link = "https://libretime.radioquantica.com/main.mp3",
        main_link = "https://www.radioquantica.com",
        about = "Rádio Quântica is a Lisbon-based community radio station established in 2015, and developed with a diverse group of artists and crews – a safe haven where the voices of underground artists and activists can be heard.",
        support_link = "https://www.paypal.com/donate?token=TeUgFAbv6YKrSZK1gda3T4X8YpPd-X6rKNAA0aRHgjwm8Gab8dfjw4L6MtTxqDQn3OPeH1o6p8VCRY7c",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Radio Raheem",
        logo = "https://internetradioprotocol.org/logos/raheem.png",
        location = "Milan",
        info_link = "https://radioraheem.airtime.pro/api/live-info-v2",
        stream_link = "https://radioraheem.out.airtime.pro/radioraheem_a",
        main_link = "https://radioraheem.it",
        about = "Radio Raheem is an independent online radio station streaming 24/7 music and visuals from Milan with a cosmic perspective. The radio, located in the Navigli area of the city, aims to support and elevate a genuine and diverse local scene while keeping an eye to the moon and the galaxies far away.",
        support_link = "https://gigastock.net/collections/radio-raheem",
        insta_link = "https://www.instagram.com/radioraheem.milano/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Radio Sygma",
        logo = "https://internetradioprotocol.org/logos/sygma.png",
        location = "Tbilisi",
        info_link = "https://radio.syg.ma/stats-icecast.json",
        stream_link = "https://radio.syg.ma/audio.mp3",
        main_link = "https://radio.syg.ma/",
        about = "radio.syg.ma is a community platform for mixes, podcasts, live recordings and releases by independent musicians, sound artists and collectives.",
        support_link = "https://radio.syg.ma/donate",
        insta_link = 'https://www.instagram.com/radiosygma/',
        bandcamp_link = 'https://radiosygma.bandcamp.com/',
        soundcloud_link = 'https://soundcloud.com/radiosygma',
        genres = ['Experimental']
),
Stream(
        name = "Rinse FR",
        logo = "https://internetradioprotocol.org/logos/rinsefr.jpg",
        location = "Paris",
        info_link = "https://www.rinse.fm/api/query/v1/schedule/",
        stream_link = "https://radio10.pro-fhi.net/flux-trmqtiat/stream",
        main_link = "https://www.rinse.fm/channels/france/",
        about = "Based in Paris, London, and all over the world with its online platforms, Rinse is a radio station but not only: label, management, curation, cultural events.",
        support_link = "https://www.rinse.fm/shop/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Rinse UK",
        logo = "https://internetradioprotocol.org/logos/rinseuk.jpg",
        location = "London",
        info_link = "https://www.rinse.fm/api/query/v1/schedule/",
        stream_link = "https://admin.stream.rinse.fm/proxy/rinse_uk/stream",
        main_link = "https://www.rinse.fm/channels/uk/",
        about = "London-based community radio station, licensed for 'young people living and/or working within the central, east and south London areas'. It plays garage, grime, dubstep, house, jungle, UK funky and other dance music genres popular in the United Kingdom.",
        support_link = "https://www.rinse.fm/shop/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "SF 10-33",
        logo = "https://internetradioprotocol.org/logos/sf1033.png",
        location = "San Francisco",
        info_link = "https://somafm.com/songs/sf1033.json",
        stream_link = "https://ice2.somafm.com/sf1033-128-mp3",
        main_link = "https://www.somafm.com",
        about = "Ambient music mixed with the sounds of San Francisco public safety radio traffic.",
        support_link = "https://somafm.com/support/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        hidden=True
),
Stream(
        name = "SWU FM",
        logo = "https://internetradioprotocol.org/logos/swu.jpg",
        location = "Bristol",
        info_link = "https://www.rinse.fm/api/query/v1/schedule/",
        stream_link = "https://admin.stream.rinse.fm/proxy/swu/stream",
        main_link = "https://www.rinse.fm/channels/swu/",
        about = "Tasked with celebrating Bristol's music culture on air, SWU FM took to the airwaves on 87.7FM for 27 days in May 2016. These historic sets from the pilot broadcast shaped the station and paved the way for SWU to secure a permanent space on the dial (103.7FM) in 2020.",
        support_link = "https://www.rinse.fm/shop/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Shared Frequencies",
        logo = "https://internetradioprotocol.org/logos/sharedfrequencies.png",
        location = "Austin",
        info_link = "https://sharedfrequencies.live/api/nowPlaying",
        stream_link = "https://sharedfrequencies.out.airtime.pro/sharedfrequencies_a",
        main_link = "https://sharedfrequencies.live",
        about = "Shared Frequencies Radio is an independent online public radio station and music blog accessible to all artists, labels, collectives and cultural partners within Texas and throughout the world. We are dedicated to providing an informational, cultural and diverse art space available to the public. Shared Frequencies Radio hosts a platform for artists to build their own unique works, and acts as a collaborative space for traveling artists to be supported.",
        support_link = "https://www.patreon.com/sharedfrequenciesradio",
        insta_link = "https://www.instagram.com/sharedfrequenciesradio/",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/sharedfrequenciesradio",
        hidden = True
),
Stream(
        name = "Skylab Radio",
        logo = "https://internetradioprotocol.org/logos/skylab.png",
        location = "Melbourne",
        info_link = "https://skylab-radio.com/api/airtime/current",
        stream_link = "https://stream.skylab-radio.com/live",
        main_link = "https://www.skylab-radio.com",
        about = "Welcome to Skylab Radio. We're an online radio station based in Melbourne, Australia. At the core we are motivated to giving a platform to presenters that don't already have one. Skylab celebrates the eclectic music, artistic flair and cultural inclusiveness canvassing this city and abroad.",
        support_link = "https://www.skylab-radio.com/subscribe",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "SomaFM Live",
        logo = "https://internetradioprotocol.org/logos/somafm.png",
        location = "San Francisco",
        info_link = "https://somafm.com/songs/live.json",
        stream_link = "https://ice2.somafm.com/live-128-mp3",
        main_link = "https://www.somafm.com",
        about = "Broadcasting from a converted warehouse in San Francisco, our high quality internet broadcasts reach around the world. Rusty Hodge, SomaFM's founder, had been experimenting with online radio since 1995. After helping other companies with their streaming media operations, he decided that no one was going to create the online radio station he wanted to listen to, so he did it himself.",
        support_link = "https://somafm.com/support/",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        hidden = True
),
Stream(
        name = "Stegi Radio",
        logo = "https://internetradioprotocol.org/logos/stegi.png",
        location = "Athens",
        info_link = "https://movementathens.airtime.pro/api/live-info-v2",
        stream_link = "https://movementathens.out.airtime.pro/movementathens_a",
        main_link = "https://stegi.radio",
        about = "STEGI.RADIO is Onassis Stegi’s online radio station, broadcasting 24 hours a day, 7 days a week. Based in Athens but looking beyond geographical borders and boundaries, STEGI.RADIO focuses on musical and cultural communities and music creation; it seeks novel ideas and sounds that reflect the new musical production as well as its historical course, creating an ever-expanding network between the cities of the Mediterranean and the rest of the globe.",
        support_link = "mailto:info@stegi.radio",
        insta_link = "https://www.instagram.com/stegiradio/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "Subtle Radio",
        logo = "https://internetradioprotocol.org/logos/subtle.jpg",
        location = "London",
        info_link = "https://subtle.airtime.pro/api/live-info-v2",
        stream_link = "https://subtle.out.airtime.pro/subtle_a",
        main_link = "https://www.subtleradio.com",
        about = "We Are Various is an online community radio station currently transmitting from inside Witzli Poetzli, Trix & Het Bos. Beats and pixels. Demos and expos. Rewinds and flashlights. Camera and musica obscura.",
        support_link = "https://www.subtle.store",
        insta_link = "https://www.instagram.com/subtleradio/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "SutroFM",
        logo = "https://internetradioprotocol.org/logos/sutrofm.jpeg",
        location = "San Francisco",
        info_link = "https://api.evenings.co/v1/streams/sutrofm/public",
        stream_link = "https://media.evenings.co/s/7Lo66BLQe",
        main_link = "https://sutrofm.net",
        about = "Online DIY radio based in the SF Bay Area.",
        support_link = "https://donate.stripe.com/28o2ai08vd4qfmMfZ1",
        insta_link = "https://www.instagram.com/sutrofm",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/sutrofm",
        hidden = True
),
Stream(
        name = "The Lot Radio",
        logo = "https://internetradioprotocol.org/logos/thelot.jpeg",
        location = "New York",
        info_link = "thelotradio.com_j1ordgiru5n55sa5u312tjgm9k@group.calendar.google.com",
        stream_link = "https://nyc-prod-catalyst-0.lp-playback.studio/hls/video+85c28sa2o8wppm58/index.m3u8",
        main_link = "https://www.thelotradio.com",
        about = "We are an independent, non-profit, online radio station live streaming 24/7 from a reclaimed shipping container on an empty lot in NYC. Expect a continuous stream of the best and most varied music New York City has to offer.",
        support_link = "https://www.paypal.com/donate/?cmd=_s-xclick&hosted_button_id=TNGKXZ2B2Z6LL&source=url&ssrt=1752175817476",
        insta_link = "https://www.instagram.com/softcircle",
        bandcamp_link = None,
        soundcloud_link = "https://www.soundcloud.com/537hmusic"
),
Stream(
        name = "Vestiges",
        logo = "https://internetradioprotocol.org/logos/vestiges.png",
        location = "Montreal",
        info_link = "https://api.evenings.co/v1/streams/vestiges/public",
        stream_link = "https://media.evenings.co/s/wL6JLe6K1",
        main_link = "https://www.are.na/vestiges/channels",
        about = "Vestiges is a World_Map, documenting new media and emergent technologies among creative communities.",
        support_link = "mailto:projectmehari@gmail.com",
        insta_link = "https://www.instagram.com/vestiges_life/",
        bandcamp_link = None,
        soundcloud_link = None,
        hidden = True
),
Stream(
        name = "Voices Radio",
        logo = "https://internetradioprotocol.org/logos/voices.jpeg",
        location = "London",
        info_link = "https://voicesradio.airtime.pro/api/live-info-v2?timezone=America/Los_Angeles",
        stream_link = "https://voicesradio.out.airtime.pro/voicesradio_a",
        main_link = "https://voicesradio.co.uk",
        about = "Previously a nomadic club series called Ossia that threw parties up and down the country over the last decade, headlined by the likes of Leon Vynehall, Chaos In The CBD, and Shanti Celeste, we rebranded as Voices in 2020 as a platform to tackle social issues through panels and events. Having released a series of podcasts over lockdown, it was a natural next step to start an online radio station, further spotlighting the community work of the network of organisers we'd met through our conversations.",
        support_link = "https://shop.voicesradio.co.uk",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "WNYU",
        logo = "https://internetradioprotocol.org/logos/wnyu.png",
        location = "New York",
        info_link = "https://lobster-app-zabc8.ondigitalocean.app/current",
        stream_link = "https://www.wnyu-ice-cast-relay.com/wnyu.mp3",
        main_link = "https://wnyu.org",
        about = "WNYU is NYU's radio station that is completely operated by NYU students. WNYU broadcasts on 89.1 FM weekdays from 4:00PM to 1:00AM, and on the Internet 24 hours a day, 7 days a week.",
        support_link = "https://www.givecampus.com/schools/NewYorkUniversity/wnyu-89-1fm-fundraiser?a=13612556",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None,
        category='Student'
),
Stream(
        name = "We Are Various",
        logo = "https://internetradioprotocol.org/logos/various.png",
        location = "Antwerp",
        info_link = "https://azuracast.wearevarious.com/api/nowplaying/we_are_various",
        stream_link = "https://azuracast.wearevarious.com/listen/we_are_various/live.mp3",
        main_link = "https://www.wearevarious.com",
        about = "We Are Various is an online community radio station currently transmitting from inside Witzli Poetzli, Trix & Het Bos. Beats and pixels. Demos and expos. Rewinds and flashlights. Camera and musica obscura.",
        support_link = "https://wearevarious.com/support-wav/",
        insta_link = "https://www.instagram.com/we_are_various/",
        bandcamp_link = None,
        soundcloud_link = None
),
Stream(
        name = "n10.as",
        logo = "https://internetradioprotocol.org/logos/n10as.png",
        location = "Montreal",
        info_link = "https://n10asmaster.herokuapp.com/radiocult/current-and-next-show",
        stream_link = "https://n10as.radiocult.fm/stream",
        main_link = "https://n10.as",
        about = "montreal based online radio station, broadcasting 24/7/365 - providing a platform for folks to create, connect and contribute to the greater community.",
        support_link = "https://www.patreon.com/n10as",
        insta_link = "https://www.instagram.com/n10.as",
        bandcamp_link = None,
        soundcloud_link = "https://soundcloud.com/n10-as"
),
Stream(
        name = "stayfm",
        logo = "https://internetradioprotocol.org/logos/stayfm.png",
        location = "Augsburg",
        info_link = "https://stayfm.com/api/v1",
        stream_link = "https://stayfm.com:8443/stream",
        main_link = "https://stayfm.com",
        about = "Founded in 2018, initially out of the desire to create an open space for audio of all kinds, stayfm has been organized as a non-profit association since 2019. Since then we are a non-commercial & independent community radio. All broadcasts are produced by club members and/or invited guests. Our goal is to promote the participation of citizens in the urban art and cultural landscape. We would like to offer DJs and musicians as well as interested (young) moderators and curators an infrastructure through which they can reach their communities of interest, share musical, artistic & socio-political topics & help shape the local media landscape.",
        support_link = "https://www.paypal.com/paypalme/radiostayfm",
        insta_link = "https://www.instagram.com/radiostayfm",
        bandcamp_link = None,
        soundcloud_link = "https://hearthis.at/stayfm/"
),
Stream(
        name = "Radio Plato",
        logo = "https://internetradioprotocol.org/logos/plato.jpg",
        location = "Minsk",
        info_link = "",
        stream_link = "https://azura.radioplato.by/public/1/playlist.m3u",
        main_link = "https://radioplato.by",
        about = "For over six years Radio Plato has been fiery dedicated, musically diverse, community-focused and what really matters: independent. We started doing radio in the fall of 2018, driven by our passion to share great music, which sometimes was lost or forgotten. Just over 2 years Radio Plato grew into a solid community of DJs, music producers, dancers, podcasters, designers and most importantly - music lovers. We rethought where we want to move and decided that our mission is to bring our community forwards.",
        support_link = "https://www.patreon.com/radioplato",
        insta_link = "https://www.instagram.com/radio_plato",
        bandcamp_link = "https://radioplato.bandcamp.com/",
        soundcloud_link = "https://soundcloud.com/radioplato",
        hidden = True
),
Stream(
        name = "Veneno",
        logo = "https://internetradioprotocol.org/logos/veneno.png",
        location = "Sao Paolo",
        info_link = "https://radio.veneno.live/api/live-info",
        stream_link = "https://radio.veneno.live/stream/main",
        main_link = "https://veneno.live/",
        about = "Created in 2018, Veneno was born from the idea of ​​unifying and solidifying the most diverse cultural initiatives. Based in downtown São Paulo, the radio today broadcasts a wide range of programs, dialoguing with different aesthetics and concepts.",
        support_link = "https://veneno.live/support-us/",
        insta_link = "https://www.instagram.com/veneno.live/",
        bandcamp_link = "",
        soundcloud_link = "",
        hidden = False
),
Stream(
        name = "Radio Relativa",
        logo = "https://internetradioprotocol.org/logos/relativa.png",
        location = "Madrid",
        info_link = "https://public.radio.co/stations/sd6131729c/status",
        stream_link = "https://streamer.radio.co/sd6131729c/listen",
        main_link = "https://radiorelativa.eu",
        about = "Radio Relativa is a community, independent, and experimental platform dedicated to promoting and connecting diverse artists and cultural initiatives from Madrid to the world. In a world saturated with content, Radio Relativa celebrates discovering and sharing culture together.",
        support_link = "https://radiorelativa.eu/support",
        insta_link = "https://www.instagram.com/relativaradio/",
        bandcamp_link = "",
        soundcloud_link = "https://soundcloud.com/radio-relativa"
),
Stream(
        name = "Radio Vilnius",
        logo = "https://internetradioprotocol.org/logos/vilnius.png",
        location = "Vilnius",
        info_link = "https://radiovilnius.live/?rest_route=/radio-vilnius-api/v1/stream-status",
        stream_link = "https://transliacija.audiomastering.lt/radiovilnius-mp3",
        main_link = "https://radiovilnius.live",
        about = "were you ever driving at 3 in the morning down some 2 lane road & it was raining & the only thing you can get on the radio is some station out of nowhere which comes in perfectly clear & plays great music like life is but a dream du wop du wop & you just turn it up & say to yourself 'where has this track been all my life?' well that’s how we feel here at the studio everyday.",
        support_link = "https://radiovilnius.live/support/",
        insta_link = "https://instagram.com/radiovilnius",
        bandcamp_link = "",
        soundcloud_link = ""
),
Stream(
        name = "Rukh Radio",
        logo = "https://internetradioprotocol.org/logos/rukh.jpg",
        location = "Odesa",
        info_link = "https://rukh.live/?qtproxycall=aHR0cHM6Ly9hMS5hc3VyYWhvc3RpbmcuY29tL2xpc3Rlbi9ydWtoL3JhZGlvLm1wMw%3D%3D&icymetadata=1&_=1781900090169",
        stream_link = "https://a1.asurahosting.com/listen/rukh/radio.mp3",
        main_link = "https://rukh.live",
        about = "RUKH (РУХ) is a non-commercial DIY community radio that focuses on alternative and experimental music, subcultures and countercultures. Broadcasting from Odesa, Ukraine.",
        support_link = "https://t.me/rukhlive",
        insta_link = "https://www.instagram.com/rukh.live/",
        bandcamp_link = "",
        soundcloud_link = "https://www.soundcloud.com/rukh-radio"
)
,
Stream(
        name = "program audio",
        logo = "https://internetradioprotocol.org/logos/program.jpg",
        location = "San Francisco",
        info_link = "https://www.twitch.tv/program_audio",
        stream_link = "https://www.twitch.tv/program_audio",
        main_link = "https://program.audio",
        about = "San Francisco-based institution. Label + Events + Radio.",
        support_link = "https://program.audio/support/",
        insta_link = "https://www.instagram.com/program.audio/",
        bandcamp_link = "https://program-audio.bandcamp.com/music",
        soundcloud_link = "https://soundcloud.com/programaudio",
        tuner_only = True
),
Stream(
        name = "KALX",
        logo = "https://internetradioprotocol.org/logos/kalx.png",
        location = "Berkeley",
        info_link = "https://kalx.studio.creek.org/api/current?x=1&studioId=29",
        stream_link = "https://stream.kalx.berkeley.edu:8443/kalx-128.mp3",
        main_link = "https://kalx.berkeley.edu",
        about = "KALX 90.7 FM broadcasts freeform radio 24 hours a day to a large portion of the San Francisco Bay Area. You can catch all stripes of underground music accented with news, sports and alternative informational programming.",
        support_link = "https://kalx.berkeley.edu/donate/",
        insta_link = "https://www.instagram.com/kalxradio/",
        tuner_only = False,
        genres = ['Student'],
        category='Student'
),
Stream(
        name = "WKCR",
        logo = "https://internetradioprotocol.org/logos/wkcr.png",
        location = "New York",
        info_link = "https://widgets.spinitron.com/widget/now-playing-v2?callback=_spinitron09910823593912169178232477166&station=wkcr&num=1&sharing=0&player=0&cover=0&merch=0",
        stream_link = "https://wkcr.streamguys1.com/live",
        main_link = "https://www.cc-seas.columbia.edu/wkcr/",
        about = "Columbia University's student-run radio station, WKCR exists to preserve and share music, the arts, and history with listeners in the New York metro area and beyond, curating programming that pushes boundaries while maintaining an eye to historical and artistic value, regardless of commercial significance.",
        support_link = "https://www.givenow.columbia.edu/?_sa=07483&_sd=411&ac=CQAU#",
        insta_link = "https://www.instagram.com/wkcr/",
        tuner_only = False,
        genres = ['Student','Jazz'],
        category = 'Student',
        status = 'Live',
        song_basis = True
),
Stream(
        name = "Datafruits FM",
        logo = "https://internetradioprotocol.org/logos/datafruits.png",
        location = "World",
        info_link = "wss://hotdog-lounge.herokuapp.com/socket/websocket?vsn=2.0.0",
        stream_link = "https://streampusher-relay.club/datafruits.mp3",
        main_link = "https://datafruits.fm/",
        about = "Datafruits is a cooperatively owned and operated free-form net radio station. This website was created by and for fans of internet radio and netlabels. Our station has little to no curation, and we believe that any song can be played.",
        support_link = "https://datafruits.fm/support",
        insta_link = "https://www.instagram.com/datafruits",
        tuner_only = False,
        status = 'Live'
),
Stream(
        name = "WCFM",
        logo = "https://internetradioprotocol.org/logos/wcfm.png",
        location = "Williamstown",
        info_link = "https://widgets.spinitron.com/widget/now-playing-v2?callback=_spinitron09910823593912169178232477166&station=wcfm&num=1&sharing=0&player=0&cover=0&merch=0",
        stream_link = "http://wcfm-streaming.williams.edu:8000/stream",
        main_link = "https://laurenkhall.nekoweb.org/website/index.html",
        about = "The voice of Williams College and the best alternative in the Berkshires. WCFM Williamstown is an FCC-licensed frequency-modulating station broadcasting on 91.9 MHz from the basement of Prospect House. Williams College radio has been around since 1940. It is the student-run voice of Williams College. WCFM programming is entirely free-form: DJs have complete control over their shows. They broadcast a beautiful mix of music, talk, and miscellaneous fun. WCFM is always open to new DJs and ways to interact with the Williams and Williamstown community.",
        support_link = "https://connect.williams.edu/portal/give-williams?tab=alumni-fund&sys:gift:notes=To%20support%20WCFM%20radio&sys:gift:field:gift_af_designations=e03106f0-d718-4726-8d2d-cac9844346c7",
        insta_link = "https://www.instagram.com/wcfmradio/",
        tuner_only = False,
        genres = ['Student'],
        category = 'Student',
        status = 'Live',
        hidden = True
),
Stream(
        name = "ChuntFM",
        logo = "https://internetradioprotocol.org/logos/chunt.png",
        location = "London",
        info_link = "https://api.chunt.org/fm/channels/1/now-playing",
        stream_link = "https://fm.chunt.org/stream",
        main_link = "https://chunt.org",
        about = '"To chunt is divine"',
        support_link = "https://ra.co/promoters/118280",
        insta_link = "https://www.instagram.com/chuntongo"
),
Stream(
        name = 'Palanga Street',
        logo = "https://internetradioprotocol.org/logos/palanga.png",
        location = 'Vilnius',
        info_link = "https://api.palanga.live/live-info-v2?shows=1",
        stream_link = 'https://stream.palanga.live/palanga128.mp3',
        main_link = 'https://palanga.live/',
        about = 'PSR is an independent community radio based in Vilnius, Lithuania. Established in 2017 in a flat on Palanga Street, we embraced a DIY philosophy that continues to inspire us to this day and fuels the engagement of our community. As a voluntary team we strive to foster a safe and inclusive environment for the creation of free cultural expression locally and online.',
        support_link = 'https://palanga.live/donate',
        insta_link = 'https://www.instagram.com/palanga_street_radio/'
),
Stream(
        name = 'Dublin Digital Radio',
        logo = "https://internetradioprotocol.org/logos/ddr.png",
        location = 'Dublin',
        info_link = "https://api.radiocult.fm/api/station/dublin-digital-radio/schedule/live",
        stream_link = 'https://dublin-digital-radio.radiocult.fm/stream',
        main_link = 'https://listen.dublindigitalradio.com/home',
        about = 'Dublin Digital Radio (ddr.) is an award-winning, online community radio station representing a wealth of alternative music, art and politics across Ireland, since 2016. ddr. is wholly funded by its members (via Patreon subscriptions), composed of listeners and broadcasters alike, ensuring that it remains independent of corporate influence and is run democratically by its growing community.',
        support_link = 'https://www.patreon.com/dublindigitalradio',
        insta_link = 'https://www.instagram.com/dublindigitalradio/',
        bandcamp_link = 'https://dublindigitalradio.bandcamp.com'
),
Stream(
        name = 'IDA',
        logo = "https://internetradioprotocol.org/logos/ida.png",
        location = 'Tallinn',
        info_link = "https://strapi.idaidaida.net/api/live",
        stream_link = 'https://broadcast.idaidaida.net:8000/stream',
        main_link = 'https://idaidaida.net',
        about = 'IDA is an online radio located in Tallinn & Helsinki.',
        support_link = 'https://idaidaida.net/about#about#support',
        soundcloud_link = 'https://soundcloud.com/ida_radio',
        insta_link = 'https://www.instagram.com/ida.radio/'
),
Stream(
        name = 'Tīrkultūra',
        logo = "https://internetradioprotocol.org/logos/tirk.png",
        location = 'Riga',
        info_link = "https://public.radio.co/api/v2/s216811754/track/current",
        stream_link = 'https://s3.radio.co/s216811754/listen.m3u',
        main_link = 'https://tirkultura.lv',
        about = 'Tīrkultūra is an interdisciplinary contemporary culture platform working mainly through the medium of sound. Tīrkultura is a listener-powered, non-commercial, and non-profit online radio station, based in Riga, Latvia.',
        support_link = 'mailto:reinis@tirkultura.net',
        soundcloud_link = 'https://soundcloud.com/tirkultura',
        insta_link = 'https://www.instagram.com/tirkultura/',
        song_basis = True
),
Stream(
        name = 'Seyðisfjörður Community Radio',
        logo = "https://internetradioprotocol.org/logos/scr.png",
        location = 'Seyðisfjörður',
        info_link = "https://www.seydisfjordurcommunityradio.net/api/schedule-live",
        stream_link = 'https://seyisfjorur-community-radio.radiocult.fm/stream',
        main_link = 'https://www.seydisfjordurcommunityradio.net/',
        about = 'A platform founded in 2016. Experimental community radio constantly in the making. Broadcasting on 107.1FM in Seyðisfjörður and online. Seyðisfjörður is a small town on Iceland’s east coast. Our radio-room is in Herðubreið Community Center. Holding our antenna up high on the roof. Connecting local residents with remote residents with anyone who tunes in. Sharing sounds of thoughts with sounds of music. Confusing radio with magic with worldbuilding with belonging. Weaving the act of listening with the act of radio-making into the act of community. An open-ended network of people and places. Glowing from transience, togetherness and a sentiment of significance. The haptic experience of keeping in touch. Through radio. Forever.',
        support_link = 'https://www.lungaschool.is/en/collaborators',
        insta_link = 'https://www.instagram.com/seydisfjordur.community.radio/',
        song_basis = True
),
Stream(
        name = 'Lahmacun',
        logo = "https://internetradioprotocol.org/logos/lahmacun.png",
        location = 'Budapest',
        info_link = "https://streaming.lahmacun.hu/api/nowplaying/1",
        stream_link = 'https://streaming.lahmacun.hu/listen/lahmacun_radio/radio.mp3',
        main_link = 'https://lahmacun.hu',
        about = 'Lahmacun.hu is an online music & more radio from Budapest.',
        support_link = 'https://lahmacun.hu/donate',
        insta_link = 'http://instagram.com/lahmacunradio',
        bandcamp_link = 'https://lahmacunradio.bandcamp.com/'
),
Stream(
        name = 'Gatekeeper Radio',
        logo = "https://internetradioprotocol.org/logos/gatekeeper.png",
        location = 'Berlin',
        info_link = "https://azuracast.gatekeeperradio.com/api/nowplaying/gatekeeper_radio",
        stream_link = 'https://azuracast.gatekeeperradio.com/listen/gatekeeper_radio/radio.mp3',
        main_link = 'https://gatekeeperradio.com/',
        about = 'GATEKEEPER RADIO represents an innovative initiative, transforming urban spaces into vibrant temporary radio stations while also launching an online platform for creative collaboration. Its bringing together creatives from the realms of art, music, science, digital media, and society, fostering connections through artistic inquiries and the exploration of new potentials.',
        support_link = 'mailto:mail@gatekeeperradio.com',
        insta_link = 'https://www.instagram.com/gatekeeper_radio/',
        song_basis = True
),
Stream(
        name = '20ft Radio',
        logo = "https://internetradioprotocol.org/logos/20ft.jpg",
        location = 'Kyiv',
        info_link = "https://api.radiocult.fm/api/station/20ft%20Radio/schedule/live",
        stream_link = 'https://20ft-radio.radiocult.fm/stream',
        main_link = 'https://20ftradio.net/',
        about = "Since 2017 we’ve been sharing music from DJs, selectors and artists from Ukraine and all over the world. Running by a small team of enthusiasts led by the idea of creating a platform for self-expression of those who are in love with music.",
        support_link = 'https://20ftradio.net/donate',
        insta_link = 'https://www.instagram.com/20ftradio/?hl=en',
        soundcloud_link = 'https://soundcloud.com/20ft_radio'
),
Stream(
        name = 'Parea Radio',
        logo = "https://internetradioprotocol.org/logos/parea.png",
        location = 'Athens',
        info_link = "https://parearadio.com/wp-json/parea/v1/live-info",
        stream_link = 'https://parea-radio-b7474105.radiocult.fm/stream',
        main_link = 'https://parearadio.com/',
        about = "Parea Radio is an independent, community-oriented online radio platform based in Athens. Rooted in the idea of parea, a circle of friends gathered around sound, the station exists as a shared space for listening, exchange and documentation. It is built around presence rather than performance, continuity rather than volume.",
        support_link = 'https://parearadio.com/support-us/',
        insta_link = 'https://www.instagram.com/parea.radio/',
        soundcloud_link = 'https://soundcloud.com/parea-radio'
),
Stream(
        name = 'Radio Dopo',
        logo = "https://internetradioprotocol.org/logos/dopo.png",
        location = 'Palermo',
        info_link = "https://public.radio.co/stations/s807721f02/status",
        stream_link = 'https://streaming.radio.co/s807721f02/listen',
        main_link = 'https://radiodopo.it/',
        about = "Established in 2025, Radio Dopo is a Palermo-based community radio station, working with artists, cultural workers and non-profit organizations, born from a partnership with like-minded community radio stations Kiosk Radio in Brussels and Refuge Worldwide in Berlin. This project has been funded by the European Union through the Erasmus+ program.",
        support_link = 'mailto:info@radiodopo.it',
        insta_link = 'https://www.instagram.com/radiodopo/',
        soundcloud_link = 'https://soundcloud.com/radiodopo'
),
Stream(
        name = 'Radio Sofa',
        logo = "https://internetradioprotocol.org/logos/sofa.png",
        location = 'Paris',
        info_link = "https://radio.radio-sofa.com/api/nowplaying/radio_sofa",
        stream_link = 'https://radio.radio-sofa.com/listen/radio_sofa/radio.mp3',
        main_link = 'https://www.radio-sofa.com/',
        about = "Radio Sofa is a collective set up in April 2020, originally in the form of a web radio, in order to participate in the continuity of the diffusion of current and electronic music in a context of closure of cultural places.",
        support_link = 'https://pay.sumup.com/b2c/QU2R9LMJ',
        insta_link = 'https://www.instagram.com/radio.sofa/',
        soundcloud_link = 'https://soundcloud.com/radio-sofa'
),
Stream(
        name = 'Sphere Radio',
        logo = "https://internetradioprotocol.org/logos/sphere.png",
        location = 'Leipzig',
        info_link = "https://libretime.sphere-radio.net/api/live-info/",
        stream_link = 'https://stream.sphere-radio.net/listen',
        main_link = 'https://www.sphere-radio.net/',
        about = "Sphere Radio is a community-driven Radio from Leipzig, curating space for diverse voices and ideas. We are open, experimental, and oriented towards emancipatory values.",
        support_link = 'https://liberapay.com/SphereRadio/',
        insta_link = 'https://www.instagram.com/sphere.radio/',
        hidden=True
),
Stream(
        name = 'Zabrij Radio',
        logo = "https://internetradioprotocol.org/logos/zabrij.png",
        location = 'Zagreb',
        info_link = "https://api.radiocult.fm/api/station/zabrij-radio/schedule/live",
        stream_link = 'https://zabrij-radio.radiocult.fm/stream',
        main_link = 'https://www.zabrijradio.org',
        about = "Zabrij Radio was established in 2025 as an open and experimental space for sound without borders. In the beginning, we explored everything, from ambient and jazz to experimental electronics, film scores, and unexpected musical corners from around the world.",
        support_link = 'https://www.zabrijradio.org/contact',
        insta_link = 'https://www.instagram.com/zabrijradio/',
        genres = ['Balkan'],
        song_basis = True
),
Stream(
        name = 'Zone Est Radio',
        logo = "https://internetradioprotocol.org/logos/zest.png",
        location = 'Strasbourg',
        info_link = "wss://radio.zest.radio/api/live/nowplaying/websocket",
        stream_link = 'https://radio.zest.radio/radio/8000/radio.mp3',
        main_link = 'https://zest.radio',
        about = "Zone Est Radio est une association et une webradio strasbourgeoise née en 2018 d'une volonté de rassembler les acteur·ices de la scène électronique locale.",
        support_link = 'mailto:zoneestradio@gmail.com',
        insta_link = 'https://www.instagram.com/zest.radio',
        soundcloud_link = 'https://soundcloud.com/zoneestradio',
        hidden = True
),
Stream(
        name = 'Depa Radio',
        logo = "https://internetradioprotocol.org/logos/depa.jpg",
        location = 'CDMX',
        info_link = "https://d36nr0u3xmc4mm.cloudfront.net/index.php/api/streaming/status/7006/41f3cd9398218d2d50bac06f1a871026/SV28BR",
        stream_link = 'https://servidor15-2.brlogic.com:7006/live?source=14465',
        main_link = 'https://depa.radio',
        about = "Transmitiendo 24/7 desde @departamento_studiobar. Música y comunidad.",
        support_link = 'https://linktr.ee/deparecords',
        insta_link = 'https://www.instagram.com/depa.radio/',
        hidden = False,
        song_basis=True
),
Stream(
        name = 'Muito Radio',
        logo = "https://internetradioprotocol.org/logos/muito.jpg",
        location = 'Buenos Aires',
        info_link = "https://muitoradio.airtime.pro/api/live-info-v2",
        stream_link = 'https://muitoradio.out.airtime.pro/muitoradio_a',
        main_link = 'https://www.muitoradio.com',
        about = "(In)dependent community radio based in Buenos Aires. With the syncretic vocation of the Brazilian tropicalist movement of the 60s, we embrace mixing as a basis and crossover as a policy, with the desire to amplify a sound that escapes the forms of production, circulation and consumption that tend to homogenise our cultural practices.",
        support_link = 'https://www.mercadopago.com.ar/subscriptions/checkout?preapproval_plan_id=05fce6105847446a9727e8cecbdbb891',
        insta_link = 'https://www.instagram.com/muitoradio/',
        soundcloud_link = 'https://soundcloud.com/muitoradio',
        hidden = False,
        song_basis=True
),
Stream(
        name = 'East Village Radio',
        logo = "https://internetradioprotocol.org/logos/evr.jpg",
        location = 'New York',
        info_link = "https://eastvillageradio.com/player-text-gw/",
        stream_link = 'https://east-village-radio.radiocult.fm/stream',
        main_link = 'https://eastvillageradio.com/',
        about = "In these times of a narrowing set of corporatized avenues for artists to gain public attention, the monopolization of virtually every singular radio station being sucking into larger platforms with profits over promotion, EVR remains committed to its original cause: a grassroots source of independent minded DJs and programmers that serves its community. Free of dictated playlists, our hosts come from a wide and diverse background, schooled and deeply knowledgable about their passion.",
        support_link = 'https://eastvillageradio.com/store/',
        insta_link = 'https://www.instagram.com/eastvillageradio',
        hidden = False,
        song_basis=True
),
Stream(
        name = 'KXLU',
        logo = "https://internetradioprotocol.org/logos/kxlu.jpg",
        location = 'Los Angeles',
        info_link = "https://spinitron.com/KXLU/",
        stream_link = 'https://kxlu.streamguys1.com/kxlu-hi',
        main_link = 'https://kxlu.com',
        about = "KXLU exists to engage in broadcasting under terms of a license granted by the Federal Communications Commission. KXLU is a non-commercial, educational station broadcasting from the Westchester campus of Loyola Marymount University at an assigned carrier of 88.9 megahertz and an assigned radiating power of 3000 watts. Licensed to the Board of Trustees of Loyola Marymount University, KXLU is operated in the public interest by its student, faculty, and volunteer staff.",
        support_link = 'https://kxlu.com/donate/',
        insta_link = 'https://www.instagram.com/kxlu/',
        hidden = False,
        song_basis= False,
        genres=['Student']
),
Stream(
        name = 'Operator Radio',
        logo = "https://internetradioprotocol.org/logos/operator.jpg",
        location = 'Rotterdam',
        info_link = "https://admin.operator-radio.com/api/sets/livenow",
        stream_link = 'https://origin.streamnerd.nl/operator/operator/icecast.audio',
        main_link = 'https://operator-radio.com/',
        about = "Operator is an online radio station and cultural platform dedicated to enriching the music and cultural landscape of Rotterdam and beyond, with a special focus on alternative sounds and underrepresented stories. We curate both on- and offline events, placing emphasis on talent development, experimentation, and nightlife culture. By putting Rotterdam on the map locally, nationally, and internationally, we showcase our creators to the world.",
        support_link = 'https://www.paypal.com/paypalme/operatorradio',
        insta_link = 'https://www.instagram.com/operator.radio/',
        hidden = False,
        song_basis= False
),
Stream(
        name = 'fbi.radio',
        logo = "https://internetradioprotocol.org/logos/fbi.jpg",
        location = 'Sydney',
        info_link = "https://admin.operator-radio.com/api/sets/livenow",
        stream_link = 'https://streamer.fbiradio.com/stream',
        main_link = 'https://fbi.radio/',
        about = "Operator is an online radio station and cultural platform dedicated to enriching the music and cultural landscape of Rotterdam and beyond, with a special focus on alternative sounds and underrepresented stories. We curate both on- and offline events, placing emphasis on talent development, experimentation, and nightlife culture. By putting Rotterdam on the map locally, nationally, and internationally, we showcase our creators to the world.",
        support_link = 'https://www.paypal.com/paypalme/operatorradio',
        insta_link = 'https://www.instagram.com/operator.radio/',
        hidden = True,
        song_basis= False
)   
]

def get_mixtapes():
    mixtapes = requests.get('https://www.nts.live/api/v2/mixtapes', timeout=TIMEOUT).json()['results']

    genre_map = {
        '4 To The Floor':['House','Techno'],
        'Expansions':['Jazz'],
        'Feelings':['Soul','Boogie'],
        'Field Recordings':['Ambient','Field Recording'],
        'Island Time':['Reggae','Dub'],
        'Labyrinth':['Electronic','Glitch'],
        'Low Key':['Lo-fi','Hip-Hop'],
        'Memory Lane':['Folk','Psychedelic'],
        'Otaku':['OST','Anime'],
        'Poolside':['Balearic','Pop'],
        'Rap House':['Trap','Drill'],
        'Sheet Music':['Classical'],
        'Slow Focus':['Ambient','Drone'],
        'Sweat':['Dance','World'],
        'The Pit':['Metal'],
        'The Tube':['Post-Punk']
    }
    
    streams = []
    for i in mixtapes:
        # get logo
        if not os.path.exists(f"logos/NTS_{i['title'].replace(' ','_')}_Corner.jpg"):
            img = Image.open(BytesIO(requests.get(i['media']['picture_medium_large']).content)).convert("RGBA")
            w, h = img.size
            s = min(w, h)
            img = img.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2))

            overlay = Image.open("assets/ntstransparent.png").convert("RGBA")
            overlay = overlay.resize((overlay.width // 2, overlay.height // 2))
            margin = 20
            ox = img.width - overlay.width - margin
            oy = img.height - overlay.height - margin
            img.paste(overlay, (ox, oy), overlay)

            img.convert("RGB").save(f"logos/NTS_{i['title'].replace(' ','_')}_Corner.jpg")
        
        if i['title'] in genre_map.keys():
            genres = genre_map[i['title']]
        else:
            genres = None

        streams.append(Stream(
            name = 'NTS ' + i['title'],
            logo = f"https://internetradioprotocol.org/logos/NTS_{i['title'].replace(' ','_')}_Corner.jpg",
            location = "World",
            info_link = "https://www.nts.live/api/v2/mixtapes",
            stream_link = i['audio_stream_endpoint'],
            main_link = 'https://www.nts.live/infinite-mixtapes/' + i['mixtape_alias'],
            show_logo = i['media']['picture_medium_large'],
            about = i['description'],
            now_playing = i['subtitle'],
            support_link =  'https://www.nts.live/supporters',
            insta_link = "https://www.instagram.com/nts_radio/",
            bandcamp_link = "",
            soundcloud_link = "",
            hidden = False,
            status = 'Re-Run',
            category = "Mixtape",
            genres=genres
        ))

    return streams

# add mixtapes to stream
streams = streams + get_mixtapes()

def process_stream(stream):

    '''
    Function for pulling existing stream info in from the dict served at /info endpoint,
    updating the stream, setting the last_updated time, and reporting errors.
    '''

    start_time = time.time()
    try:
        stream.update()
        stream.update_one_line()
        stream.process_logos()
        stream.set_last_updated()

        processing_time = time.time() - start_time
        print(f"{stream.name} took {processing_time:.2f} seconds")
        
        return (stream.name, stream.to_dict())
    except Exception:
        error = f'[{datetime.now()}] Error updating {stream.name}:\n{traceback.format_exc()}\n'
        print(stream.name, 'Error')
        return (stream.name, error, stream.hidden)

def main_loop():
    last_processed = {}  # stream name -> epoch of last processing

    while True:
        try:
            start_time = time.time()
            now = time.time()

            with open('info.json', 'r') as f:
                prior_values = json.load(f)

            # pick streams due for processing based on their interval
            due_streams = []
            for stream in streams:
                interval = 20 if getattr(stream, 'song_basis', False) else 90
                last = last_processed.get(stream.name, 0)
                if now - last >= interval:
                    due_streams.append(stream)

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(process_stream, s): s for s in due_streams}
                results = []
                for future in futures:
                    results.append(future.result(timeout=60))
                    last_processed[futures[future].name] = time.time()

            processing_time = time.time() - start_time
            error_dict = {}
            updated = {}

            for result in results:
                if len(result) == 3:
                    name, err, hidden_status = result
                    if hidden_status != True:
                        error_dict[name] = err
                    if name in prior_values.keys():
                        prior_values[name]['hidden'] = hidden_status
                        updated[name] = prior_values[name]
                else:
                    name, val = result
                    if isinstance(val, dict):
                        if (val['oneLiner'] != [i.one_liner for i in streams if i.name == name][0]) & (val['status'] != 'Offline'):
                            updated[name] = val
                        else:
                            updated[name] = [i.to_dict() for i in streams if i.name == name][0]
                    else:
                        print(val, name)

            # carry forward streams that weren't reprocessed this cycle
            for name, val in prior_values.items():
                if name not in updated:
                    updated[name] = val

            with open('info.json', 'w') as f:
                json.dump(updated, f, indent=4, sort_keys=True, default=str)

            error_lines = [val for key, val in error_dict.items()]
            with open('errorlog.txt', 'w') as log:
                log.write('\n'.join(error_lines))

            now = time.time()
            url = 'https://gateway-us.umami.is/api/websites/8362bf37-0d81-4f25-9ee8-027269410e08/stats?startAt=0&endAt=' + str(round(now) * 1000)

            headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'Authorization': 'Bearer 0P6H7A9QO/j67Iw0dkYmAgvf61YVd+1DwoGh3LVsAELR69R5giXNGaJ4UgKlf6qy3QSH5+sCy3/LnT2JXXeoIzGzQE0AqZa5iZZjXZuE2ET/CcLM8OrxQfMgk9rHYJuQ2VssWSlAVPezymVaWZtAB6XpuE+55umTux1+znIPZm9tHAMBv/vmZ9u8izKWWAXjnR9HHuAIZVcKwWdOj+301DjAyaQ3P0HVOVv00J0zhH/voraRMtOVZtOwcuWKxYFU9O6nbKnR8k/1auGT+gOodRQDPyLq6HEIWbW7ZVUoUZe4DVgMo69K+oWqXbbRiogoKvZXSlTkw583JVTXJbeunjhrTg4DndskkdGxzw==',
                'Origin': 'https://cloud.umami.is',
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.1 Safari/605.1.15',
                'x-umami-share-context': '1',
                'x-umami-share-token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzaGFyZUlkIjoiMmZlMThjZTktMTNlNi00MzA5LTk0MTQtODJiNTcxOTJhZmEzIiwic2hhcmVUeXBlIjoxLCJwYXJhbWV0ZXJzIjp7InV0bSI6ZmFsc2UsImdvYWxzIjpmYWxzZSwiZXZlbnRzIjpmYWxzZSwiY29tcGFyZSI6ZmFsc2UsImZ1bm5lbHMiOmZhbHNlLCJyZXZlbnVlIjpmYWxzZSwiam91cm5leXMiOmZhbHNlLCJvdmVydmlldyI6dHJ1ZSwicmVhbHRpbWUiOmZhbHNlLCJzZXNzaW9ucyI6ZmFsc2UsImJyZWFrZG93biI6ZmFsc2UsInJldGVudGlvbiI6ZmFsc2UsImFsbG93RmlsdGVyIjp0cnVlLCJhdHRyaWJ1dGlvbiI6ZmFsc2UsInBlcmZvcm1hbmNlIjpmYWxzZX0sIndlYnNpdGVJZCI6IjgzNjJiZjM3LTBkODEtNGYyNS05ZWU4LTAyNzI2OTQxMGUwOCIsInR5cGUiOiJzaGFyZSIsImlhdCI6MTc4NDA5MjMxMH0.TKWhqRst0ZOpwUtF7DU77SAv2ffCPnBKfxs6I_oaZrw',
            }

            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode())

            status = {
                'last_updated_epoch': now,
                'last_updated_utc': datetime.fromtimestamp(now, tz=pytz.timezone('UTC')),
                'last_updated_et': datetime.fromtimestamp(now, tz=pytz.timezone('America/New_York')),
                'last_updated_pt': datetime.fromtimestamp(now, tz=pytz.timezone('America/Los_Angeles')),
                'errors': [key for key, val in error_dict.items()],
                'total': len(updated),
                'hidden': len([key for key, val in updated.items() if (val['hidden'] == True) or (val['tunerOnly'] == True)]),
                'live': len([key for key, val in updated.items() if val['hidden'] != True and val['status'] == 'Live']),
                're-run': len([key for key, val in updated.items() if val['hidden'] != True and val['status'] == 'Re-Run']),
                'offline': len([key for key, val in updated.items() if val['hidden'] != True and val['status'] == 'Offline']),
                'stations': [key for key, val in updated.items()],
                'hits': data['pageviews']
            }

            taglines = [
                f'{status["total"] - status["hidden"]} of the best independent, human-curated radio stations for the non-algorithmic, palate-expanding, music discovery pleasure of those unafraid to listen through friction.',
                'As soon as the generals and the politicos can predict the motions of your mind, lose it.',
                'Radiation from computer screens is boiling your eyes. Use your ears.'
            ]
            status['app_tagline'] = taglines[datetime.fromtimestamp(time.time()).hour % len(taglines)]

            with open('status.json', 'w') as f:
                json.dump(status, f, indent=4, sort_keys=False, default=str)

            print(f'Done! Total time {processing_time}')
            print('-' * 50)
            time.sleep(10) 

        except Exception as e:
            print(f"Error in main loop: {e}")
            traceback.print_exc()
            print('-' * 50)
            time.sleep(10)

if __name__ == '__main__':
    main_loop()