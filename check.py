from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
    show_logo = v['showLogo']
    now = datetime.now(timezone.utc)
    seconds_since_last_update = (now - datetime.fromisoformat(last_updated)).seconds

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

    if show_logo:
        try:
            with session.get(show_logo, timeout=5) as r:
                show_logo_resp = r.status_code
        except requests.exceptions.RequestException:
            show_logo_resp = 0
    else:
        show_logo_resp = None

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

        if (show_logo_resp!=200) | (show_logo_resp!=None):
            review_list.append(f'Show logo unresponsive ({v['showLogo']})')

    needs_review = len(review_list)>0
    review_str = ', '.join(review_list)
    
    status = {
        '-nowPlaying':now_playing,
        'toReview':review_str,
        'minutesSinceLastUpdated':round(seconds_since_last_update / 60, 1),
        'name':v['name'],
        'hidden':hidden,
        'status':status,
        'logo':logo_resp,
        'mainLink':v['mainLink'],
        'showLogo':show_logo_resp,
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

            to_review = {k:v for k,v in statuses.items() if v['needsReview']==True}
            for k,v in to_review.items():
                del v['needsReview']
                del v['hidden']
                del v['name']
            stations = ', '.join([k for k,_ in to_review.items()])

            check_dict = {
                'lastChecked': datetime.now(timezone.utc),
                'needsReview': len(to_review.keys()),
                'review':to_review,
                'statuses':statuses
            }

            with open('check.json','w') as f:
                json.dump(check_dict, f, indent=4, sort_keys=True, default=str)

            hour = datetime.now(timezone.utc).hour
            if len(stations) > 0 and (hour >= 14 or hour < 4): 
                send_email(stations, to_review)
                
        except Exception as e:
            print('Issue with checks.', e)

        time.sleep(60 * 60 * 3) 
    
if __name__ == '__main__':
    main_loop()