from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from tqdm import tqdm
import requests 
import pprint
import json
import time
import os

def check(v):
    print(v['name'])
    session = requests.Session()
    now_playing = v['nowPlaying']
    hidden = v['hidden'] 
    status = v['status']
    last_updated = v['lastUpdated']
    seconds_since_last_update = (datetime.now(timezone.utc) - datetime.fromisoformat(last_updated)).seconds

    # check endpoint statuses
    try:
        logo_resp = session.get(v['logo'], timeout=3).status_code
    except requests.exceptions.RequestException:
        logo_resp = 0

    try:
        with session.get(v['streamLink'], stream=True, timeout=5) as r:
            stream_resp = r.status_code
    except requests.exceptions.RequestException:
        stream_resp = 0

    try:
        info_link = v['infoLink'] if 'calendar.google.com' not in v['infoLink'] else f"https://www.googleapis.com/calendar/v3/calendars/{v['infoLink']}/events"
        info_resp = session.get(info_link, timeout=3).status_code
    except requests.exceptions.RequestException:
        info_resp = 0
    
    # get items to review
    review_list = []
    if hidden == False:
        if (now_playing==None or now_playing=='') and status!='Offline':
            review_list.append('Blank now playing')

        if stream_resp!=200 and status!='Offline':
            review_list.append(f'Stream unresponsive ({v['streamLink']})')

        if info_resp!=200 and (seconds_since_last_update >= 300):
            review_list.append(f'Info unresponsive ({v['infoLink']})')
        
        if logo_resp!=200:
            review_list.append(f'Logo unresponsive ({v['logo']})')

    needs_review = len(review_list)>0
    review_str = ', '.join(review_list)
    
    status = {
        '-nowPlaying':now_playing,
        'toReview':review_str,
        'secondsSinceLastUpdated':round(seconds_since_last_update / 60, 1),
        'name':v['name'],
        'hidden':hidden,
        'status':status,
        'logo':logo_resp,
        'info':info_resp,
        'stream':stream_resp,
        'needsReview':needs_review,
    }

    return v['name'], status


import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(stations, to_review):

    '''
    Function for emailing myself errors.
    '''

    msg = MIMEMultipart()
    msg['From'] = 'brayden@braydenmoore.com'
    msg['To'] = 'brayden@braydenmoore.com'
    msg['Subject'] = f'Review {stations}'
    msg.attach(MIMEText(pprint.pformat(to_review).replace("},","\n\n").replace(": {","\n").replace('{','').replace('}','').replace("'",'').replace('-nowPlaying: ','')))
    try:
        with open('environ.json','r') as f:
            passw = json.load(f)['GMAIL_PASS']
    except:
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
    info_up = False
    try:
        data = requests.get('https://one-radio.com/info', timeout=3).json()
        info_up = True
    except:
        send_email('One-Radio', 'Could not get from /info')

    if info_up:
        try:
            streams = data.keys()

            with ThreadPoolExecutor(max_workers=10) as executor:
                    futures = [executor.submit(check, data[stream]) 
                            for stream in streams]
                    results = [future.result(timeout=60) for future in futures]

            print('-'*50)
            statuses = {i[0]: i[1] for i in results}

            with open('check.json','w') as f:
                json.dump(statuses, f, indent=4, sort_keys=True, default=str)

            to_review = {k:v for k,v in statuses.items() if v['needsReview']==True}
            for k,v in to_review.items():
                del v['needsReview']
                del v['hidden']
                del v['name']
            stations = ', '.join([k for k,_ in to_review.items()])

            if len(stations)>0:
                send_email(stations, to_review)
        except:
            print('Issue with checks.')

    time.sleep(60 * 60)
    
if __name__ == '__main__':
    main_loop()