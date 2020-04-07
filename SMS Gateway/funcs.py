import os
import re
import syslog
import json
import uuid
import requests
from datetime import datetime
from slackclient import SlackClient
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

logFile = '/var/log/smsd'
messageLog = '/var/log/ses_messages'
baseDir = '/packages/sms/'
filesDir = baseDir + 'etc/'
wolMap = filesDir + 'name_sms_map'
specMap = filesDir + 'special-name_sms_map'
slackToken = 'REDACTED'
apiUrl = 'https://api.ses.nsw.gov.au/sms'
apiKey = 'REDACTED'
apiHeaders = {'Content-type': 'application/json', 'Ocp-Apim-Subscription-Key': apiKey}
debug = False

##  Logging

def log(msg):
    logTs = datetime.now().strftime('%d/%m/%y %H:%M:%S')
    if debug is True:
        print(logTs + ' ' + msg)
    else:
        lf = open(logFile, 'a')
        lf.write(logTs + ' ' + msg + '\n')
        lf.close()
        syslog.openlog(ident='smsd')
        syslog.syslog(msg)
        syslog.closelog()

def logMsg(sender, dest, msg):
    logTs = datetime.now().strftime('%d/%m/%y %H:%M')
    logMsg = sender + ' -> ' + dest + ': ' + msg
    if debug is True:
        print(logMsg)
    else:
        lf = open(messageLog, 'a')
        lf.write(logTs + ' ' + logMsg + '\n')
        lf.close()
        if 'Reminder:' not in msg:
            syslog.syslog((syslog.LOG_LOCAL2 | syslog.LOG_INFO), logMsg)

##  Return the name belonging to a number

def lookupWolSms(num):
    with open(wolMap,'r') as f:
        for line in f:
            if num in line:
                return line.split(':')[1].rstrip()

def lookupSpecialSms(num):
    with open(specMap,'r') as f:
        for line in f:
            if num in line:
                return line.split(':')[1].rstrip()

def lookupName(num):
    sender = lookupWolSms(num)
    if sender is not None:
        return sender
    sender = lookupSpecialSms(num)
    if sender is not None:
        return sender
    return 'Unknown'

##  Cleanup a phone number

def cleanNumber(n):
    number = '0' + n[3:] if '+' in n else n
    return number

##  Message processing functions

def cleanup(msg):
    stripped = (c for c in msg if 0 < ord(c) < 127)
    msg = ''.join(stripped)
    msg = re.sub('Call SOC.*', '', msg)
    msg = re.sub('Check SCC.*', '', msg)
    return msg

def smsIgnore(sender, msg):
    if sender == 'Unknown' and 'http:' in msg:  # Spam
        return True 
    if 'SHQSEZ' in msg:                         
        return True

##  Return a list of SMS recipients for a destination (filename)

def smsRecipients(dest):
    recips = []
    for d in dest.split(','):
        if 'Beacon' in d:
            continue
        recipsFile = filesDir + d
        if os.access(recipsFile, os.R_OK):
            with open(recipsFile, 'r') as f:
                for line in f:
                    if line == 'None':
                        continue
                    if '@' in line:
                        recips.append(line.split('@')[0].rstrip().replace(' ',''))
                    else:
                        recips.append(line.rstrip().replace(' ',''))
        else:
            log(f'No SMS recipients file for {d}')
    return list(set(recips))

##  Slack notifications post

def slackPost(sender, dest, msg):
    text = msg + '\n:arrow_left: ' + sender + '\n:arrow_right: ' + dest + '\n'
    icon_url = 'https://mystic.ses.nsw.gov.au/sms-icon.png'
    channel='REDACTED'
    name = 'SMS'
    attachment = {
        'title': msg,
        'fields': [
            {'title': 'Sender', 'value': sender, 'short': True},
            {'title': 'Destinations', 'value': dest, 'short': True},
        ]
    }
    sc = SlackClient(slackToken)
    r = sc.api_call('chat.postMessage', channel=channel, username=name, icon_url=icon_url, attachments=[attachment])
    if r['ok']:
        log('Slack message posted')
        return r['ts']
    else:
        log('slackPost failed: ' + r['error'])
        return None

def slackComment(thread, msg):
    icon_url = 'https://mystic.ses.nsw.gov.au/sms-icon.png'
    name = 'SMS'
    channel = 'REDACTED'
    sc = SlackClient(slackToken)
    r = sc.api_call('chat.postMessage', channel=channel, thread_ts=thread, text=msg, username=name, icon_url=icon_url)
    if r['ok']:
        log('Slack comment posted')
        return r['ts']
    else:
        log('slackComment failed: ' + r['error'])
        return None

##  Send SMS via SES API

def apiSmsSend(dest, msg, ts):
    payload = {
        'Content': msg,
        'DestinationNumbers': dest,
        'CallbackUrl': 'http://lhq.wollongong.ses.nsw.gov.au:8443/',
        'Metadata': {'ts': ts}
    }

    try:
        r = requests.post(apiUrl, data=json.dumps(payload), headers=apiHeaders)
    except:
        log(f'apiSmsSend: POST to {apiUrl} failed')
        return None
    if r.status_code != requests.codes.accepted:
        log(f'apiSmsSend: Response code {r.status_code} - {r.text}')
        return None
    else:
        return r.json()
