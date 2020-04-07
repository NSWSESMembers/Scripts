import time
import json
from datetime import datetime
from dateutil import tz
import funcs

statFile = '/var/www/html/smsstat.json'
deliveryStatuses = ['queued', 'enroute', 'submitted', 'delivered', 'failed', 'rejected', 'expired']
threads = []

##  Return a summary string
def summary():
    numThreads = len(threads)
    activeThreads = 0
    stats = {x: 0 for x in deliveryStatuses}
    for t in threads:
        active = 0
        for r in t['Recipients']:
            if deliveryStatuses.index(r['Status']) < deliveryStatuses.index('submitted'):
                active = 1
            stats[r['Status']] += 1
        activeThreads += active
    return f'{numThreads} threads ({activeThreads} active) - ' + json.dumps(stats)

##  Send a new message
def sendMsg(sender, message, ts, slack, recipients):
    recips = []
    response = funcs.apiSmsSend(recipients, message, ts)
    if response is None:
        funcs.slackComment(ts, 'Failed to send message via SMS API')
        return
    for r in response:
        number = funcs.cleanNumber(r['DestinationNumber'])
        recips.append({'Recipient': number, 'Name': funcs.lookupName(number), 'MsgId': r['MessageId'], 'Status': r['Status'], 'Updated': ''})
    if recips:
        content = response[0]['Content']
        threads.append({'Sender': sender, 'Message': content, 'Ts': ts, 'Slack': slack, 'Sent': False, 'Recipients': recips})
        if content != message:
            funcs.log(f'sendMsg: message was "{message}" but content is "{content}"')

##  Process a delivery report
def deliveryReport(dr):
    number = funcs.cleanNumber(dr['source_number'])
    status = dr['status']
    ts = dr['metadata']['ts']
    msgid = dr['message_id']
    if status not in deliveryStatuses:
        funcs.log(f'deliveryReport: Unknown status {status}')
        return None
    # Find thread and recipient
    thread = next((t for t in threads if t['Ts'] == ts), None)
    if thread is None:
        funcs.log(f'deliveryReport: Could not find thread for "{msgid}"')
        return None
    recipient = next((r for r in thread['Recipients'] if r['Recipient'] == number), None)
    if recipient is None:
        funcs.log(f'deliveryReport: Could not find recipient {number} in thread {ts}')
        return None
    # Update recipient
    if deliveryStatuses.index(status) > deliveryStatuses.index(recipient['Status']):
        funcs.log(f'deliveryReport: {number} is {status}')
        dt = datetime.strptime(dr['date_received'][:-5], '%Y-%m-%dT%H:%M:%S').replace(tzinfo=tz.tzutc())
        lt = dt.astimezone(tz.tzlocal()).strftime('%H:%M:%S')
        recipient['Status'] = status
        recipient['Updated'] = lt
    return ts

##  Return the number of recipients for a message
def msgRecips(ts):
    thread = next((t for t in threads if t['Ts'] == ts), None)
    return len(thread['Recipients']) if thread is not None else None

##  Has a message been sent to all recipients
def msgSent(ts):
    thread = next((t for t in threads if t['Ts'] == ts), None)
    if thread is None:
        funcs.log(f'msgSent: Could not find thread for ts {ts}')
        return False
    for r in thread['Recipients']:
        if r['Status'] not in ['submitted', 'delivered', 'rejected', 'failed']:
            return False
    if not thread['Sent']:
        thread['Sent'] = True
        return True
    else:
        return False    # Only return true the first time all messages have been sent 

##  Is there a slack post for this thread

def isSlackThread(ts):
    thread = next((t for t in threads if t['Ts'] == ts), None)
    if thread is None:
        funcs.log(f'isSlackThread: Could not find thread for ts {ts}')
        return False
    return thread['Slack']

##  Cleanup threads

def cleanup():
    cleanTime = time.time() - (24 * 60 * 60)
    count = 0
    for t in threads:
        active = False
        ts = t['Ts']
        if float(ts) < cleanTime:
            count += 1
            for r in t['Recipients']:
                if r['Status'] in ['enroute', 'submitted']:
                    active = True
            if active:
                funcs.log(f'cleanup: Warning - thread {ts} had undelivered messages')
            threads.remove(t)
    if count:
        funcs.log(f'cleanup: Removed {count} old threads')
    # Update stat file
    try:
        sf = open(statFile, 'w')
        sf.write(json.dumps(threads))
        sf.close()
    except:
        log(f'Could not update {statFile}')
