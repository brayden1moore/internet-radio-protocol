from datetime import datetime, timezone, timedelta, date
from concurrent.futures import ThreadPoolExecutor
from bs4 import BeautifulSoup
import traceback
import requests
import shutil
import time
import json
import re

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

def to_one_line(stream):
    parts = [
        stream['nowPlaying'],
        stream['nowPlayingArtist'],
        stream['nowPlayingSubtitle'],
        stream['nowPlayingAdditionalInfo'],
    ]
    return_string = " - ".join(p for p in parts if p)
    if len(return_string) > 100:
        return_string = return_string[:100] + '...'
    return return_string

def write_main_page(streams):
    latest_time_utc, latest_time_pt, latest_time_et, latest_name = get_latest_time(streams)
    streams = dict(sorted(streams.items(), key=lambda item: item['lastUpdated']))
    main_text = '<br>'.join(
        ['<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Internet Radio Protocol</title></head><body style="font-family:Andale Mono; padding:50px;">',
        '<b>The Internet Radio Protocol</b> is a simple, standardized hub of information with direct streaming links and real-time now playing data for an ever-expanding list of internet radio stations.',
        '',
        'You can access the information by going to <a href="https://internetradioprotocol.org/info">internetradioprotocol.org/info</a>',
        'The list currently includes:',
        '',''
        '<br>'.join([f'<div style="align-items: center; display: flex;"><audio controls style="width:40px;" src="{v["streamLink"]}"></audio><img width="65px" height="65px" style="margin-left:10px; margin-right:10px; border: 1px solid black;" src="{v["logo"]}"</img> <div> <a target="_blank" href="{v['mainLink']}">{k}</a><br>{to_one_line(v)}<br>{v["location"]}<br>{v["status"]}</div></div>' for k,v in streams.items()]),
        '',
        'And the last update was made at:',
        f"{latest_time_utc} (UTC)",
        f"{latest_time_pt} (PT)",
        f"{latest_time_et} (ET)",
        f'to {latest_name}',
        '',
        'If you have any questions, comments, or radio station addition suggestions, please email <a href="mailto:brayden.moore@icloud.com">brayden.moore@icloud.com</a>.'
        '</body></html>',
        '<style> @font-face {font-family: "Andale Mono";src: url("assets/andalemono.ttf") format("truetype");}</style>'
        ]
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

        if type(from_dict) == dict:
            self.name = from_dict['name']
            self.logo = from_dict['logo']
            self.location = from_dict['location']
            self.info_link = from_dict['infoLink']
            self.stream_link = from_dict['streamLink']
            self.main_link = from_dict['mainLink']
            self.about = from_dict['about']
            self.status = from_dict['status']
            self.now_playing_artist = from_dict['nowPlayingArtist']
            self.now_playing = from_dict['nowPlaying']
            self.now_playing_subtitle = from_dict['nowPlayingSubtitle']
            self.now_playing_description = from_dict['nowPlayingDescription']
            self.now_playing_description_long = from_dict['nowPlayingDescriptionLong']
            self.additional_info = from_dict['nowPlayingAdditionalInfo']
            self.show_logo = from_dict['showLogo']
            self.insta_link = from_dict['instaLink']
            self.bandcamp_link = from_dict['bandcampLink']
            self.soundcloud_link = from_dict['soundcloudLink']
            self.last_updated = from_dict['lastUpdated']

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

            "lastUpdated": self.last_updated
        }
    
    def update(self):
        if "internetradioprotocol.org" not in self.logo:
            self.logo = "https://internetradioprotocol.org/" + self.logo

        if self.name in ['HydeFM','SutroFM']:
            info = requests.get(self.info_link).json()
            self.status = "Online" if info['online'] == True else "Offline"
            if self.status == "Online":
                try: 
                    self.now_playing_artist = info['name'].strip().split(' w/ ')[1] # artist name like "Vitamin 1K (Benji)"
                    self.now_playing = info['name'].strip().split(' w/ ')[0] # show name like "Super Supplement"
                except:
                    self.now_playing = info.get('name', self.name).strip() # full title like "Super Supplement w/ Vitamin 1k (Benji)"
            self.additional_info = f"{info['listeners']} listener{s(info['listeners'])}" # listener count 


        elif 'NTS' in self.name:
            info = requests.get(self.info_link).json()
            result_idx = 0 if self.name == 'NTS 1' else 1

            now = info['results'][result_idx]['now']
            self.now_playing = clean_text(now['broadcast_title']) # show name like "In Focus: Timbaland"
            self.location = now['embeds']['details']['location_long'] # location like "New York"
            self.show_logo = now['embeds']['details']['media']['background_large'] or self.show_logo # show-specific logo if provided
            try:
                self.now_playing_description_long =  clean_text(now['embeds']['details']['description']) # full description
                self.now_playing_description =  clean_text(now['embeds']['details']['description'])[:44] + '...' # abridged description
            except:
                pass
            
            genres = []
            for g in now['embeds']['details']['genres']:
                genres.append(g['value'].strip())

            self.additional_info = ', '.join(genres) # genre list if provided

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
                    self.show_logo = program['attachments'] or self.show_logo # show-specific logo if provided
                    try:
                        self.now_playing_description_long = clean_text(program['description']) # long description of the show
                        self.now_playing_description = clean_text(program['description'])[:44] + '...'  # abridged description
                    except:
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
                pass


        elif self.name == 'Voices Radio': 
            info = requests.get(self.info_link).json()
            if not info['shows']['current']:
                self.status = 'Offline'
            else:
                self.status = 'Online'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # just artist name if possible like "Willow"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[0]) # just show name if posible like "Wispy"
                except:
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ','').replace('.mp3','')) # full title like "Wispy w/ Willow"


        elif self.name == 'Kiosk Radio': 
            info = requests.get(self.info_link).json()
            if not info['shows']['current']:
                self.status = 'Offline'
            else:
                self.now_playing  = clean_text(info['shows']['current']['name']) # broadcast name like "Staff Picks" or "Piffy (live)"
                self.status = 'Online'
                try:
                    self.now_playing_artist  = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # artist names like "Fa_Fane & F.M."
                    self.now_playing_subtitle = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[0]) # episode title "Delodio"
                except:
                    self.now_playing_subtitle = clean_text(info['tracks']['current']['name'].replace(' - ',' ').replace('.mp3','')) # full title like "Badlcukwind plays Drowned By Locals"'


        elif self.name == 'Do!!You!!! World': 
            info = requests.get(self.info_link).json()

            if not info['shows']['current']:
                self.status = 'Offline'
            else:
                self.status = 'Online'
                try:
                    self.now_playing_artist = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split(' w/ ')[1]) # artist name like "Charlemagne Eagle"
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','').split('w/')[0]) # show name like "The Do!You!!! Breakfast Show"
                except:
                    self.now_playing = clean_text(info['shows']['current']['name'].replace(' - ',' ').replace('.mp3','')) # show name like "The Do!You!!! Breakfast Show w/ Charlemagne Eagle"

        elif self.name == 'Radio Quantica':
            info = requests.get(self.info_link).json()

            self.now_playing = info['currentShow'][0]['name'] # show name like "NIGHT MOVES"
            try:
                self.now_playing_subtitle = info['current']['name'] # track name if provided
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
                        description_lines = event['description'].split('\n')
                        self.now_playing_description = clean_text(description_lines[0])[:44] + '...' # short desc like "A late night special with Kem Kem playing from the heart ..."
                        self.now_playing_description_long = clean_text(description_lines[0]) # long desc 
                        self.additional_info = clean_text(description_lines[-1]) # genre list like "World, Jazz, Afrobeats, Electronic"
                        
                        for l in description_lines[1:-1]:
                            l = clean_text(l)
                            if 'instagram.' in l.lower():
                                self.insta_link = l
                            elif 'bandcamp.' in l.lower():
                                self.bandcamp_link = l
                            elif 'soundcloud.' in l.lower():
                                self.soundcloud_link = l   
                    except:
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
                        pass

        elif self.name == 'We Are Various':
            info = requests.get(self.info_link).json()
            self.status = 'Online' if info['is_online'] == True else 'Offline'
            self.additional_info = f"{info['listeners']['current']} listener{s(info['listeners']['current'])}" # listener count if available
            self.now_playing = info['now_playing']['song']['title'] # simple show title

        elif self.name == 'Lower Grand Radio':
            info = requests.get(self.info_link).json()
            if not info['shows']['current']:
                self.status = 'Offline'
            else:
                self.status = 'Online'
                self.now_playing = info['shows']['current']['name'] # simple show title
            
        elif self.name == 'KJazz':
            webpage = requests.get(self.main_link).text
            soup = BeautifulSoup(webpage, 'html.parser')
            self.now_playing_artist = soup.find_all("a", "noDec")[1].get_text() # host name

        elif self.name == 'KEXP':
            now_utc = datetime.now(timezone.utc)
            song = requests.get(self.info_link).json()['results'][0]
            show_uri = song['show_uri']
            show = requests.get(show_uri).json()

            self.now_playing_artist = ', '.join(show['host_names']) # concatenation of host names
            self.now_playing = show['program_name'] # concatenation of host names show name
            self.now_playing_additional_info = show['program_tags'] # genre list
            self.show_logo = show['program_image_uri'] # show logo if provided

            if song['play_type'] == 'trackplay':
                self.now_playing_subtitle = f"{song['song']} by {song['artist']}" # last played song and artist
        
        elif self.name == 'Clyde Built Radio':
            info = requests.get(self.info_link).json()
            self.now_playing = info['shows']['current']['name'] # just song name

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

    def set_last_updated(self):
        self.last_updated = datetime.now(timezone.utc)


if __name__ == '__main__':
    while True:
        with open('info.json','r') as f:
            stream_json = json.load(f)

        error_lines = []

        def process_stream(kv):
            name, value = kv
            stream = Stream(from_dict=value)

            try:
                stream.update()
                updated_dict = stream.to_dict()
                if value != updated_dict:
                    stream.set_last_updated()
                    return (stream.name, stream.to_dict())
                else:
                    print('No update for', stream.name)
                    return (stream.name, value)
            except Exception:
                error_lines.append(f'[{datetime.now()}] Error updating {stream.name}:\n')
                error_lines.append(traceback.format_exc() + '\n')
                return (stream.name, value)

        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(process_stream, stream_json.items())

        stream_json = dict(results)

        with open('info.json','w') as f:
            json.dump(stream_json, f, indent=4, sort_keys=True, default=str)

        with open('errorlog.txt', 'w') as log:
            log.writelines(error_lines)

        write_main_page(stream_json)

        time.sleep(60)