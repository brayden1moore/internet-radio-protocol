from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
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
import re
import io
import os

logging.disable()

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
                value_list = value

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

    def __init__(self, from_dict=None, name=None, logo=None, location=None, info_link=None, stream_link=None, main_link=None, about=None, support_link=None, insta_link=None, bandcamp_link=None, soundcloud_link=None, hidden=False, genres=None):
        # station info 
        self.name = name
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

        # show info
        self.status = "Online"
        self.now_playing_artist = None
        self.now_playing = None
        self.now_playing_subtitle = None
        self.now_playing_description = None
        self.now_playing_description_long = None
        self.additional_info = None
        self.show_logo = None
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
            "genres":self.genres
        }

    
    def update(self):

        '''
        The main function for fetching updated now-playing data for each station. 
        Each "if" statement contains unique logic for gathering and processing station metadata.
        '''

        if "internetradioprotocol.org" not in self.logo:
            self.logo = "https://internetradioprotocol.org/" + self.logo

        if self.name == 'HydeFM':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['shows','current','name'])
            self.status = "Online" if self.now_playing else "Offline"
                
        if self.name in ['SutroFM','Lower Grand Radio','Vestiges']:
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['name'])
            self.additional_info = None 
            self.listeners = extract_value(info, ['listeners'], rule='listeners')
            self.show_logo = extract_value(info, ['image'])
            self.now_playing_description_long = extract_value(info, ['description'])
            self.now_playing_description = extract_value(info, ['description'], rule='shorten')
            self.status = "Online" if info['online'] == True else "Offline"

        elif 'NTS' in self.name:
            info = requests.get(self.info_link).json()
            result_idx = 0 if self.name == 'NTS 1' else 1
            now = info['results'][result_idx]['now']
            self.now_playing = extract_value(now, ['broadcast_title'])  # show name like "In Focus: Timbaland"
            self.location = extract_value(now, ['embeds','details','location_long']) or 'London' # location like "New York"
            self.show_logo = extract_value(now, ['embeds','details','media','background_large'])
            self.now_playing_description_long =  extract_value(now, ['embeds','details','description']) # full description
            self.now_playing_description =  extract_value(now, ['embeds','details','description'], rule='shorten') # abridged description
            self.now_playing_subtitle = extract_value(now, ['embeds', 'details','moods'], sub_location=['value'], rule='list')
            self.additional_info = None# extract_value(now, ['embeds', 'details','genres'], sub_location=['value'], rule='list')
            self.genres = extract_value(now, ['embeds', 'details','genres'], sub_location=['value'], rule='list_genres')

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
                if program.get('startTime'):
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
            info = requests.get(self.info_link).json()
            self.additional_info = None
            self.now_playing_artist = None
            self.genres = ['Student']

            if info['metadata']:
                self.now_playing = extract_value(info,['metadata','playlist_title'])
                self.now_playing_artist = extract_value(info,['metadata','dj'])
                self.additional_info = extract_value(info,['metadata','release_title'])
            else:
                self.now_playing = extract_value(info,['playlist','title'])

            self.show_logo = extract_value(info,['playlist','image'])
             
            if info['metadata']['artist_name'] and self.additional_info:
                self.additional_info += ' by ' + extract_value(info,['metadata','artist_name'])
            if info['metadata']['release_year'] and self.additional_info:
                self.additional_info += " (" + str(extract_value(info,['metadata','release_year'])) + ")"

            self.now_playing_description_long = extract_value(info,['playlist','description'])
            self.now_playing_description = extract_value(info,['playlist','description'], rule='shorten')

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
            if not info['shows']['current']['name']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
                self.now_playing_subtitle = None
            else:
                self.now_playing  = extract_value(info, ['shows','current','name']) # broadcast name like "Staff Picks" or "Piffy (live)"
                self.status = 'Online'
                self.now_playing_subtitle = extract_value(info, ['tracks','current','name']) # episode title "Delodio"

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

        elif self.name == 'Radio Raheem': 
            info = requests.get(self.info_link).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

        elif self.name == 'Stegi Radio': 
            info = requests.get(self.info_link).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

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
            self.additional_info = None 
            self.now_playing = None
            self.now_playing_description = None
            self.now_playing_description_long = None                

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
                        
                        last_line = clean_text(description_lines[-1])  # genre list like "World, Jazz, Afrobeats, Electronic"
                        if last_line:
                            if '.' not in last_line:
                                self.additional_info = last_line 
                        
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
            info = requests.get(self.info_link + today + '?cachebust=' + str(random.randint(0,10000))).json()
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
            self.additional_info = None
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['title'] # simple show title

        elif self.name == 'KWSX':
            info = requests.get(self.info_link).json()
            self.status = 'Online' if info['is_online'] == True else 'Offline'
            self.additional_info = None 
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['text'] # simple show title

        elif self.name == 'KJazz':
            webpage = requests.get(self.main_link).text
            soup = BeautifulSoup(webpage, 'html.parser')
            self.now_playing = soup.find_all("a", "noDec")[1].get_text() # host name
            self.now_playing_artist = None

        elif self.name == "Particle FM":
            info = requests.get(self.info_link).json()[0]
            self.additional_info = None 
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            rerun = ' (R)' if not info['live']['is_live'] else ''
            self.now_playing = info['now_playing']['song']['title'] + rerun

        elif self.name == 'KEXP':
            now_utc = datetime.now(timezone.utc)
            info = requests.get(self.info_link)
            song = info.json()['results'][0]
            show_uri = song['show_uri']
            show = requests.get(show_uri).json()

            self.now_playing_artist = ', '.join(show['host_names']) # concatenation of host names
            self.now_playing = show['program_name'] # concatenation of host names show name
            self.additional_info = None
            self.genres = show['program_tags'].split(',')
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
                info = requests.get(self.info_link).json()
                self.now_playing = info['tracks']['current']['metadata']['track_title']
                self.status = "Online"
            except:
                self.now_playing = None
                self.status = "Offline"

        elif self.name == 'LYL Radio':
            info = requests.post(self.info_link,data={"variables":{},"query":"{\n  onair {\n    title\n    hls\n    __typename\n  }\n}\n"})
            try:
                self.now_playing = info.json()['data']['onair']['title']
                if "WE'LL BE BACK" not in self.now_playing:
                    self.status = 'Online'
                else:
                    self.status = 'Offline'
            except:
                self.now_playing = None
                self.status = 'Offline'
        
        elif self.name == 'Skylab Radio':
            info = requests.get(self.info_link).json()

            self.now_playing = None
            self.additional_info = None
            self.show_logo = None
            self.status = "Offline"

            try:
                self.now_playing = info['currentShow'][0]['name']
                self.additional_info = info['current']['track_title'] + ' by '+ info['current']['artist_name']
                self.status = "Online"
            except:
                try:
                    self.now_playing = info['currentShow'][0]['name']
                    self.status = "Online"
                except:
                    pass

            try:
                self.show_logo = info['metadata']['artwork_url']
            except:
                self.show_logo = None
        
        elif self.name == 'BFF.fm':
            info = requests.get(self.info_link).json()
            self.now_playing = info['program']
            self.now_playing_artist = info['presenter']
            try:
                self.now_playing_subtitle = info['title'] + ' by ' + info['artist']
            except:
                self.now_playing_subtitle = info['title']
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
        
        elif self.name == 'Radio Alhara':
            info = requests.get(self.info_link).json()
            self.now_playing = info['title']
            self.now_playing_artist = info['artist']
        
        elif self.name == 'Mutant Radio':
            info = requests.get(self.info_link).json()
            self.now_playing = info['title']

        elif self.name == 'n10.as':
            info = requests.get(self.info_link).json()
            self.now_playing = info['currentShow'][0]['name']
            self.additional_info = 'Next: ' + info['nextShow'][0]['name']

        elif self.name == 'Radio Banda Larga':
            info = requests.get(self.info_link).json()
            try:
                self.now_playing = info['shows']['current']['name'].upper()
                if self.now_playing == 'TA':
                    self.now_playing = 'Picks from the archive'
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'Subtle Radio':
            info = requests.get(self.info_link).json()
            try:
                self.now_playing = info['shows']['current']['name']
                self.now_playing_description = info['shows']['current']['description']
                self.additional_info = info['tracks']['current']['name'].lstrip(' - ').replace('.mp3','')
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == "Monotonic Radio":
            info = requests.get(self.info_link).json()

            self.status = "Offline"
            try:
                self.now_playing = info['now_playing']
                self.status = "Online"
                if info['source'] == 'live':
                    self.stream_link = 'http://monotonicradio.com:8000/stream.m3u'
                else: 
                    self.stream_link = 'https://monotonicradio.com/stream'
            except:
                pass
            self.now_playing_description = info.get('video_description')
            self.genres = extract_value(info, ['genres'], rule='list_genres')
             
        elif self.name == 'HKCR':

            stream_url = self.stream_link
            tmp_file = tempfile.mktemp(suffix='.jpg')
            
            subprocess.run([
                'ffmpeg', '-i', stream_url, '-frames:v', '1',
                '-vf', 'crop=in_w*0.45:in_h*0.038:in_w*0.037:in_h*0.035,eq=contrast=3.0,format=gray',
                tmp_file, '-hide_banner', '-y'
            ], capture_output=True)
            
            if os.path.exists(tmp_file):
                result = subprocess.run(['tesseract', tmp_file, 'stdout'],
                                    capture_output=True, text=True)
                os.remove(tmp_file)
                self.now_playing = result.stdout.strip().strip('-').strip("'").strip(':').strip('Live - ').strip('? - ')
            '''
            info = requests.get(self.info_link).json()
            if len(info) > 0:
                self.now_playing = extract_value(info[0], ['title'])
            '''
            
        elif self.name == 'CKUT':
            info = requests.get(self.info_link).json()
            self.genres = ['Student']
            self.now_playing = info['program']['title_html']
            self.now_playing_description_long = clean_text(info['program']['description_html'])
            if len(self.now_playing_description_long) > 44:
                self.now_playing_description = clean_text(info['program']['description_html'])[:44] + '...'
            else: 
                self.now_playing_description = clean_text(info['program']['description_html'])

        elif self.name == 'KUSF':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['now','title'])
            self.now_playing_subtitle = extract_value(info, ['Track','title'])
            self.now_playing_description = extract_value(info, ['now','short_description'])
            self.now_playing_description_long = extract_value(info, ['now','full_description'])
            self.now_playing_artist = extract_value(info, ['now','hosts',0,'display_name'])
            self.additional_info = None #extract_value(json=info, location=['now','categories'], sub_location=['title'], rule='list')
            self.genres = ['Student']
            genres = extract_value(json=info, location=['now','categories'], sub_location=['title'], rule='list_genres')
            if genres:
                self.genres.extend(genres)

        elif self.name == 'Shared Frequencies':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['current','metadata','track_title'])
            self.now_playing_artist = extract_value(info, ['current','metadata','artist_name'])
            if not self.now_playing:
                self.status = 'Offline'
            else:
                self.status = 'Live'

        elif self.name == 'Radio Nopal':
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

        elif self.name == 'Noods Radio':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['result','content','title'])

        elif self.name == 'Radio Punctum':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['data','title'])
            self.now_playing_artist = extract_value(info, ['data','artists'], ['name'], rule='list')

        elif self.name == 'Radio 80000':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['currentShow',0,'name'])
            self.status = "Online" if self.now_playing else "Offline"
        
        elif self.name == 'stayfm':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['showQueued','title'])
            self.now_playing_artist = extract_value(info, ['showQueued','host'])
            if info['onair'] == 'archive':
                self.stream_link = info['streamArchive']
            else:
                self.stream_link = info['streamLive']

        elif self.name == 'Oroko Radio':
            info = requests.get(self.info_link).json()
            self.now_playing = extract_value(info, ['result','metadata','title'])
            self.now_playing_artist = extract_value(info, ['result','metadata','artist'])
            self.show_logo = extract_value(info, ['result','metadata','artwork','default'])

        elif self.name == 'Desire Path Radio':
            ch2_info = requests.get(self.info_link).json()
            self.status = 'Offline'
            if ch2_info['online'] == True:
                info = ch2_info
                self.status = 'Live'
                self.genres = ['Talk']
            else:
                info = requests.get(self.info_link.replace('-channel-2','')).json()
                if info['online'] == True:
                    self.status = 'Live'
                    self.genres = None
            
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
            info = requests.get(self.info_link).json()
            now_playing_append = ' (R)' if extract_value(info, ['currentShow',0,'auto_dj']) == True else ''
            self.now_playing = extract_value(info, ['currentShow',0,'name']) + now_playing_append

        elif self.name == 'Radio Relativa':
            info = requests.get(self.info_link).json()
            self.status = 'Live' if extract_value(info, ['status']) == 'online' else 'Offline'
            self.now_playing = extract_value(info, ['current_track','title']).replace('Live Now - ', '')

        elif self.name == 'Radio Vilnius':
            info = requests.get(self.info_link).json()
            self.now_playing = None
            self.now_playing_artist = None
            self.status = 'Offline'
            self.listeners = None
                
            for i in info['allStats']:
                if 'server_name' in i.keys():
                    if i['server_name'] == 'Radio Vilnius':
                        self.now_playing = extract_value(i, ['title'])
                        self.now_playing_artist = extract_value(i, ['artist'])
                        self.status = "Live"
                        self.listeners = extract_value(i, ['listener_peak'])
                        
        elif self.name == 'Rukh Radio':
            info = requests.get(self.info_link).text
            self.now_playing = info
    
        elif self.name == 'Pan African Space Station':
            info = requests.get(self.info_link).json()
            self.now_playing_artist = extract_value(info, ['current','metadata','artist_name'])
            self.now_playing = extract_value(info, ['current','metadata','track_title']) or ''
            self.now_playing = self.now_playing.replace('.mp3','')

        elif self.name == 'Refuge Worldwide':
            info = requests.get(self.info_link).json()
            self.status = 'Live' if info['status'] == 'online' else 'Offline'
            self.show_logo = info, ['liveNow', 'artwork']
            self.now_playing = extract_value(info, ['liveNow','title']).split(' - ')[0]
            try:
                self.now_playing_artist = extract_value(info, ['liveNow','title']).split(' - ')[1]
            except:
                self.now_playing_artist = None


    def set_last_updated(self):
        self.last_updated = datetime.now(timezone.utc)

    def update_one_line(self):
        parts = [
            self.now_playing,
            self.now_playing_artist,
            self.now_playing_subtitle,
            self.additional_info,
        ]
        return_string = " - ".join(p for p in parts if p).replace(' - - ',' - ')

        self.one_liner = return_string

        rerun_strs = ['rotazione notte','night moves','night files','repeats','(r)', 're-run', 're-wav', 'restream', 'playlist','replays','stayfmix','picks from the archive','archivo','subtle selects']

        if self.status != 'Offline':
            self.status = 'Live'
            if any(string in self.one_liner.lower() for string in rerun_strs) or self.name == 'Monotonic Radio':
                self.status = 'Re-Run'
            if self.status == 'Live':
                date1 = re.search("([0-9]{2}\/[0-9]{2}\/[0-9]{4})", self.one_liner)
                if date1:
                    date = datetime.strptime(date1.group(), "%d/%m/%Y")
                    if date < datetime.now():
                        self.status = 'Re-Run'
                else:
                    date2 = re.search("([0-9]{2}\.[0-9]{2}\.[0-9]{2})", self.one_liner)
                    if date2:
                        try:
                            date = datetime.strptime(date2.group(), "%m.%d.%y")
                        except:
                            date = datetime.strptime(date2.group(), "%d.%m.%y")      
                        if date:                      
                            if date < datetime.now():
                                self.status = 'Re-Run'

    def process_logos(self):
        logo_file = self.logo.replace('https://internetradioprotocol.org/','')

        tmp = {}
        logo = Image.open(logo_file).convert('RGB')

        logo_96 = logo.resize((96,  96)).convert('RGB')
        logo_60 = logo.resize((60,  60)).convert('RGB')
        logo_25 = logo.resize((25,  25)).convert('RGB')
        logo_176 = logo.resize((176, 176)).convert('RGB')           

        # save images to dict
        tmp['logo_96'] = logo_96
        tmp['logo_60']  = logo_60
        tmp['logo_25'] = logo_25
        tmp['logo_176'] = logo_176

        # save images to lib
        for i in ['96','60','25','176']:
            entire_path = f'logos/{self.name.replace(' ','_')}_{i}.pkl'
            with open(entire_path, 'wb') as f:
                pickle.dump(tmp[f'logo_{i}'], f)


## define streams
streams = [
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
        soundcloud_link = None
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
        soundcloud_link = "https://soundcloud.com/radiockut"
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
        info_link = "https://cms.hkcr.live/schedule/current",
        stream_link = "https://stream.hkcr.live/hls/stream_high.m3u8",
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
        info_link = "https://hydefmradio.airtime.pro/api/live-info-v2",
        stream_link = "https://hydefmradio.out.airtime.pro/hydefmradio_a",
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
        info_link = "https://c11.radioboss.fm/w/nowplayinginfo?u=270",
        stream_link = "https://c11.radioboss.fm:18270/stream",
        main_link = "https://www.internetpublicradio.live",
        about = "Internet Public Radio is an independent cultural platform and radio station curated by local and international DJs, musicians and visual artists.",
        support_link = "https://www.internetpublicradio.live",
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
        soundcloud_link = None
),
Stream(
        name = "KJazz",
        logo = "https://internetradioprotocol.org/logos/kjazz.webp",
        location = "Long Beach",
        info_link = "",
        stream_link = "https://das-edge11-live365-dal03.cdnstream.com/a49833/playlist.m3u8",
        main_link = "https://www.kkjz.org",
        about = "KKJZ 88.1 FM (“KJazz”) is the #1 full-time mainstream jazz station in the United States and one of the top ranked public radio stations in the country.",
        support_link = "https://kkjz.secureallegiance.com/kkjz/WebModule/Donate.aspx?P=WEB2020&PAGETYPE=PLG&CHECK=RmCkD65dLKTtDFdmd%2bo4ruzWDeZ%2beA1M",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
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
        genres = ['Talk']
),
Stream(
        name = "KUSF",
        logo = "https://internetradioprotocol.org/logos/kusf.png",
        location = "San Francisco",
        info_link = "http://www.kusf.org/api/broadcasting",
        stream_link = "https://listen.kusf.org/stream",
        main_link = "http://www.kusf.org/",
        about = "KUSF is the University of San Francisco's online radio station. KUSF as an FM station was known both nationally and internationally for its innovative programming and approach to music. From 1963 until 2011, KUSF was a student-run broadcast station owned by the University of San Francisco. Following the frequency's sale, KUSF announced plans to become an online-only station.",
        support_link = "https://www.givecampus.com/campaigns/7449/donations/new?pdesignation=kusf",
        insta_link = "https://www.instagram.com/kusforg",
        bandcamp_link = "https://kusforg.bandcamp.com",
        soundcloud_link = None
),
Stream(
        name = "KWSX",
        logo = "https://internetradioprotocol.org/logos/kwsx.png",
        location = "International",
        info_link = "https://stream.kwsx.online/api/nowplaying/kwsx",
        stream_link = "https://stream.kwsx.online/listen/kwsx/radio.mp3",
        main_link = "https://radio.kwsx.online",
        about = "KWSX is the bleeding-edge of digital online radio. Created by a like-minded collective of freaks, KWSX cares to give music the space it needs to breathe. Radiation from the computer screens is boiling our eyes. Use your ears.",
        support_link = "https://ko-fi.com/kwsxradio",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
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
        soundcloud_link = "https://soundcloud.com/imogensmusic"
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
        hidden = True
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
        info_link = "https://rblmedia.airtime.pro/api/live-info-v2?timezone=America/Los_Angeles",
        stream_link = "https://rblmedia.out.airtime.pro/rblmedia_a",
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
        soundcloud_link = "https://soundcloud.com/radiopunctum"
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
        location = "International",
        info_link = "https://radio.syg.ma/stats-icecast.json",
        stream_link = "https://radio.syg.ma/audio.mp3",
        main_link = "https://radio.syg.ma/",
        about = "radio.syg.ma is a community platform for mixes, podcasts, live recordings and releases by independent musicians, sound artists and collectives.",
        support_link = "https://radio.syg.ma/donate",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
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
        support_link = "https://www.subtle.store/supporters",
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
        stream_link = "https://lax-prod-catalyst-0.lp-playback.studio/hls/video+85c28sa2o8wppm58/1_0/index.m3u8?tkn=0PXtAu1v6ORkXaY0CeQxFt",
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
        support_link = "https://wnyu.org/contacts/send-us-music",
        insta_link = None,
        bandcamp_link = None,
        soundcloud_link = None
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
        info_link = "https://veneno.airtime.pro/api/live-info",
        stream_link = "https://veneno.out.airtime.pro/veneno_b",
        main_link = "https://veneno.live/",
        about = "Created in 2018, Veneno was born from the idea of ​​unifying and solidifying the most diverse cultural initiatives. Based in downtown São Paulo, the radio today broadcasts a wide range of programs, dialoguing with different aesthetics and concepts.",
        support_link = "https://veneno.live/support-us/",
        insta_link = "https://www.instagram.com/veneno.live/",
        bandcamp_link = "",
        soundcloud_link = "",
        hidden = True
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
        info_link = "https://rukh.live/?qtproxycall=aHR0cHM6Ly9hMS5hc3VyYWhvc3RpbmcuY29tL2xpc3Rlbi9ydWtoL3JhZGlvLm1wMw%3D%3D&icymetadata=1",
        stream_link = "https://a1.asurahosting.com/listen/rukh/radio.mp3",
        main_link = "https://rukh.live",
        about = "RUKH (РУХ) is a non-commercial DIY community radio that focuses on alternative and experimental music, subcultures and countercultures. Broadcasting from Odesa, Ukraine.",
        support_link = "https://t.me/rukhlive",
        insta_link = "https://www.instagram.com/rukh.live/",
        bandcamp_link = "",
        soundcloud_link = "https://www.soundcloud.com/rukh-radio"
)
]

def add_info_to_index(stream_json):
    with open('index.html', 'r') as f:
        html_content = f.read()

    json_str = json.dumps(stream_json)
    injection = f'''<!-- STATION_DATA_START -->
                    <script>window.STATION_DATA = {json_str};</script>
                    <!-- STATION_DATA_END -->'''

    html_content = re.sub(
        r'<!-- STATION_DATA_START -->.*?<!-- STATION_DATA_END -->',
        '',
        html_content,
        flags=re.DOTALL
    )

    html_content = html_content.replace('</head>', f'{injection}</head>')
    with open('index.html', 'w') as f:
        f.write(html_content)


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
        return (stream.name, error)

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(error_dict):

    '''
    Function for emailing myself errors.
    '''
    has_other_errors = False
    has_json_errors = False
    has_timeout_errors = False

    need_to_send = False

    if isinstance(error_dict, dict):
        other_errors = 'Errors: \n'
        json_errors = '\n\nJSON Decode Errors: \n'
        timeout_errors = '\n\nTimeout Errors: \n'
        for name, err in error_dict.items():
            if 'JSONDecodeError' in err:
                json_errors += name + '\n'
                has_json_errors = True
            elif 'ReadTimeoutError' in err:
                timeout_errors += name + '\n'
                has_timeout_errors = True
            elif 'ConnectTimeoutError' in err:
                timeout_errors += name + '\n'
                has_timeout_errors = True     
            elif 'RemoteDisconnected' in err:
                timeout_errors += name + '\n'
                has_timeout_errors = True                            
            else:
                other_errors += f'\n\n{name}: \n {err}'
                has_other_errors = True

        body = other_errors + json_errors + timeout_errors
        if (has_other_errors==True):
            need_to_send = True
        #need_to_send = True
    
    else:
        body = '\n'.join([val for _,val in error_dict.items()])
    
    if need_to_send == True:
        msg = MIMEMultipart()
        msg['From'] = 'brayden@braydenmoore.com'
        msg['To'] = 'brayden@braydenmoore.com'
        msg['Subject'] = 'New Error(s) On IRP'
        msg.attach(MIMEText(body, 'plain'))
        passw = os.environ.get('GMAIL_PASS')

        try:
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login("brayden@braydenmoore.com", passw)
                server.send_message(msg)
                print('Email Sent')
        except Exception as e:
            print('Email Failed')
            print(e)

def main_loop():

    '''
    Loop that brings the above functions together. 
    1. Reads the current info.json 
    2. Writes the internetradioprotocol.org homepage from it
    3. Processes each station with ThreadPoolExecutor
    4. Writes the newly gathered information to info.json
    5. Emails me the errors
    '''

    while True:
        try:
            start_time = time.time()

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_stream, stream) 
                        for stream in streams]
                results = [future.result() for future in futures]

            processing_time = time.time() - start_time

            error_dict = {}
            updated = {}

            for result in results:
                if len(result) == 3:
                    name, val, err = result
                    error_dict[name] = err
                else:
                    name, val = result
                    if isinstance(val, dict):
                        if (val['oneLiner'] != [i.one_liner for i in streams if i.name == name][0]) & (val['status'] != 'Offline'):
                            updated[name] = val
                        else:
                            updated[name] = [i.to_dict() for i in streams if i.name == name][0]
                    else:
                        print(val, name)

            with open('info.json', 'w') as f:
                json.dump(updated, f, indent=4, sort_keys=True, default=str)

            try:
                with open('errorlog.txt', 'r') as log:
                    existing_lines = log.read().split('\n')
            except FileNotFoundError:
                existing_lines = ['']
            
            error_lines = [val for key, val in error_dict.items()]
            #if len(' '.join(error_lines)) != len(' '.join(existing_lines)):
            send_email(error_dict)

            with open('errorlog.txt', 'w') as log:
                log.write('\n'.join(error_lines))

            print(f'Done! Total time {processing_time}')
            time.sleep(60)
        except KeyboardInterrupt:
            print("Shutting down gracefully...")
            break
        except Exception as e:
            print(f"Error in main loop: {e}")
            traceback.print_exc()
            time.sleep(60)    

if __name__ == '__main__':
    main_loop()