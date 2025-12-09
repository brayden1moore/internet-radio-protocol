from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo
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
        self.one_liner = None
        self.support_link = None
        self.hidden = None
        self.listeners = None
        self.genres = None

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
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['shows','current','name'])
            self.status = "Online" if self.now_playing else "Offline"
                
        if self.name in ['SutroFM','Lower Grand Radio','Vestiges']:
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['name'])
            self.additional_info = None 
            self.listeners = extract_value(info, ['listeners'], rule='listeners')
            self.show_logo = extract_value(info, ['image'])
            self.now_playing_description_long = extract_value(info, ['description'])
            self.now_playing_description = extract_value(info, ['description'], rule='shorten')
            self.status = "Online" if info['online'] == True else "Offline"

        elif 'NTS' in self.name:
            info = requests.get(self.info_link, timeout=10).json()
            result_idx = 0 if self.name == 'NTS 1' else 1
            now = info['results'][result_idx]['now']
            self.now_playing = extract_value(now, ['broadcast_title'])  # show name like "In Focus: Timbaland"
            self.location = extract_value(now, ['embeds','details','location_long']) or 'London' # location like "New York"
            self.show_logo = extract_value(now, ['embeds','details','media','background_large'])
            self.now_playing_description_long =  extract_value(now, ['embeds','details','description']) # full description
            self.now_playing_description =  extract_value(now, ['embeds','details','description'], rule='shorten') # abridged description
            self.now_playing_subtitle = extract_value(now, ['embeds', 'details','moods'], sub_location=['value'], rule='list')
            self.additional_info = extract_value(now, ['embeds', 'details','genres'], sub_location=['value'], rule='list')
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
            info = requests.get(self.info_link, timeout=10).json()

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
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing_additional_info = None
            self.now_playing_artist = None

            if info['metadata']:
                self.now_playing = extract_value(info,['metadata','playlist_title'])
                self.now_playing_artist = extract_value(info,['metadata','dj'])
                self.now_playing_additional_info = extract_value(info,['metadata','release_title'])
            else:
                self.now_playing = extract_value(info,['playlist','title'])

            self.show_logo = extract_value(info,['playlist','image'])
             
            if info['metadata']['artist_name'] and self.now_playing_additional_info:
                self.now_playing_additional_info += ' by ' + extract_value(info,['metadata','artist_name'])
            if info['metadata']['release_year'] and self.now_playing_additional_info:
                self.now_playing_additional_info += " (" + str(extract_value(info,['metadata','release_year'])) + ")"

            self.now_playing_description_long = extract_value(info,['playlist','description'])
            self.now_playing_description = extract_value(info,['playlist','description'], rule='shorten')

        elif self.name == 'Voices Radio': 
            info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()

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
            info = requests.get(self.info_link, timeout=10).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

        elif self.name == 'Stegi Radio': 
            info = requests.get(self.info_link, timeout=10).json()

            if not info['shows']['current']:
                self.status = 'Offline'
                self.now_playing = None
                self.now_playing_artist = None
            else:
                self.status = 'Online'
                self.now_playing = clean_text(info['shows']['current']['name']) # show name like "The Do!You!!! Breakfast Show"

        elif self.name == 'Radio Quantica':
            info = requests.get(self.info_link, timeout=10).json()

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
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['nowplaying']
            
        elif self.name == 'KQED':
            today = date.today().isoformat()
            epoch_time = int(time.time())
            info = requests.get(self.info_link + today, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()
            self.status = 'Online' if info['is_online'] == True else 'Offline'
            self.additional_info = None
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['title'] # simple show title

        elif self.name == 'KWSX':
            info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()[0]
            self.now_playing_additional_info = None 
            self.listeners = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            rerun = ' (R)' if not info['live']['is_live'] else ''
            self.now_playing = info['now_playing']['song']['title'] + rerun

        elif self.name == 'KEXP':
            now_utc = datetime.now(timezone.utc)
            info = requests.get(self.info_link, timeout=10)
            song = info.json()['results'][0]
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
            info = requests.get(self.info_link, timeout=10).json()
            try:
                self.now_playing = info['shows']['current']['name'] # just song name
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'SF 10-33':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['songs'][0]['title']
            self.now_playing_artist = info['songs'][0]['artist']
            self.now_playing_subtitle = info['songs'][0]['album']
        
        elif self.name == 'SomaFM Live':
            info = requests.get(self.info_link, timeout=10).json()
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

            info = requests.get(self.info_link, timeout=10).json()
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
                info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()

            self.now_playing = None
            self.now_playing_additional_info = None
            self.show_logo = None
            self.status = "Offline"

            try:
                self.status = "Online"
                self.now_playing = info['currentShow'][0]['name']
                self.now_playing_additional_info = info['current']['track_title'] + ' by '+ info['current']['artist_name']
            except:
                try:
                    self.status = "Online"
                    self.now_playing = info['currentShow'][0]['name']
                except:
                    pass

            try:
                self.show_logo = info['metadata']['artwork_url']
            except:
                self.show_logo = None
        
        elif self.name == 'BFF.fm':
            info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['title']
            self.now_playing_artist = info['artist']
        
        elif self.name == 'Mutant Radio':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['title']

        elif self.name == 'n10.as':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['currentShow'][0]['name']
            self.additional_info = 'Next: ' + info['nextShow'][0]['name']

        elif self.name == 'Radio Banda Larga':
            info = requests.get(self.info_link, timeout=10).json()
            try:
                self.now_playing = info['shows']['current']['name'].upper()
                if self.now_playing == 'TA':
                    self.now_playing = 'Picks from the archive'
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == 'Subtle Radio':
            info = requests.get(self.info_link, timeout=10).json()
            try:
                self.now_playing = info['shows']['current']['name']
                self.now_playing_description = info['shows']['current']['description']
                self.additional_info = info['tracks']['current']['name'].lstrip(' - ').replace('.mp3','')
                self.status = 'Online'
            except:
                self.now_playing = None
                self.status = 'Offline'

        elif self.name == "Monotonic Radio":
            info = requests.get(self.info_link, timeout=10).json()

            self.status = "Offline"
            try:
                self.now_playing = info['now_playing']
                self.status = "Online"
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
                self.now_playing = result.stdout.strip().strip('-').strip("'").strip(':').strip('Live - ')

        elif self.name == 'CKUT':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = info['program']['title_html']
            self.now_playing_description_long = clean_text(info['program']['description_html'])
            if len(self.now_playing_description_long) > 44:
                self.now_playing_description = clean_text(info['program']['description_html'])[:44] + '...'
            else: 
                self.now_playing_description = clean_text(info['program']['description_html'])

        elif self.name == 'KUSF':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['now','title'])
            self.now_playing_subtitle = extract_value(info, ['Track','title'])
            self.now_playing_description = extract_value(info, ['now','short_description'])
            self.now_playing_description_long = extract_value(info, ['now','full_description'])
            self.now_playing_artist = extract_value(info, ['now','hosts',0,'display_name'])
            self.additional_info = extract_value(json=info, location=['now','categories'], sub_location=['title'], rule='list')
            self.genres = extract_value(json=info, location=['now','categories'], sub_location=['title'], rule='list_genres')

        elif self.name == 'Shared Frequencies':
            info = requests.get(self.info_link, timeout=10).json()
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
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['result','content','title'])

        elif self.name == 'Radio Punctum':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['data','title'])
            self.now_playing_artist = extract_value(info, ['data','artists'], ['name'], rule='list')

        elif self.name == 'Radio 80000':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['currentShow',0,'name'])
            self.status = "Online" if self.now_playing else "Offline"
        
        elif self.name == 'stayfm':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['showQueued','title'])
            self.now_playing_artist = extract_value(info, ['showQueued','host'])
            if info['onair'] == 'archive':
                self.stream_link = info['streamArchive']
            else:
                self.stream_link = info['streamLive']

        elif self.name == 'Oroko Radio':
            info = requests.get(self.info_link, timeout=10).json()
            self.now_playing = extract_value(info, ['result','metadata','title'])
            self.now_playing_artist = extract_value(info, ['result','metadata','artist'])
            self.show_logo = extract_value(info, ['result','metadata','artwork','default'])

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
                        date = datetime.strptime(date2.group(), "%m.%d.%y")
                        if date < datetime.now():
                            self.status = 'Re-Run'

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


def process_stream(name, value):

    '''
    Function for pulling existing stream info in from the dict served at /info endpoint,
    updating the stream, setting the last_updated time, and reporting errors.
    '''

    start_time = time.time()
    stream = Stream(from_dict=value)
    try:
        stream.update()
        stream.update_one_line()
        stream.set_last_updated()

        processing_time = time.time() - start_time
        print(f"{name} took {processing_time:.2f} seconds")
        
        return (stream.name, stream.to_dict())
    except Exception:
        error = f'[{datetime.now()}] Error updating {stream.name}:\n{traceback.format_exc()}\n'
        return (stream.name, value, error)

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
            else:
                other_errors += f'\n\n{name}: \n {err}'
                has_other_errors = True

        body = other_errors + json_errors + timeout_errors
        if (has_other_errors==True) or (has_json_errors==False & has_other_errors==False & has_timeout_errors==False):
            need_to_send = True
    
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
                print('EmailSent')
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
            with open('info.json', 'r') as f:
                stream_json = json.load(f)

            add_info_to_index(stream_json)

            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(process_stream, name, val) 
                        for name, val in stream_json.items()]
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
                updated[name] = val

            with open('info.json', 'w') as f:
                json.dump(updated, f, indent=4, sort_keys=True, default=str)

            try:
                with open('errorlog.txt', 'r') as log:
                    existing_lines = log.read().split('\n')
            except FileNotFoundError:
                existing_lines = ['']
            
            error_lines = [val for key, val in error_dict.items()]
            if len(' '.join(error_lines)) != len(' '.join(existing_lines)):
                send_email(error_dict)

            with open('errorlog.txt', 'w') as log:
                log.write('\n'.join(error_lines))

            print('Done!')
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