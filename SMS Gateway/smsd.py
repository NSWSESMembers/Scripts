#!/usr/bin/env python3

import os
import sys
from datetime import datetime
import paho.mqtt.client as mqttSub
import paho.mqtt.publish as mqttPub
import time
import json
import re
import funcs
import sms

sys.path.append('/packages/beacon/scripts')
from beaconapi import Beacon

mqttServer = 'localhost'
blockedSenders = ['0422726874']
beaconGroups = {'WOL_Beacon_All': 'WOL - All Members - Normal', 'DPT_Beacon_All': 'DPT - All Members - Normal',
                'WOL_Beacon_Test': 'WOL - Test'}

# MQTT Callbacks

def mqttConnected(client, userdata, flags, rc):
    funcs.log('Connected to MQTT server ' + mqttServer)
    client.subscribe('/SMSGW/smsfrom/#', qos=1)
    client.subscribe('/sms/smsto/#', qos=1)
    client.subscribe('/smsapi/deliveryreport', qos=1)
    client.subscribe('/nagios/smsd', qos=1)

def mqttReceived(client, userdata, msg):
    message = msg.payload.decode('utf-8')

    # Nagios health checks
    if msg.topic == '/nagios/smsd':
        if message == 'ping':
            message = sms.summary()
            mqttPub.single('/nagios/smsd', message, qos=1, hostname=mqttServer)
            funcs.log(message)
            sms.cleanup()
        return

    # Messaging
    topicType = msg.topic.split('/')[2]
    if topicType != 'deliveryreport':
        topicArg = msg.topic.split('/')[3]
        if len(topicArg) == 0:
            funcs.log('mqttReceived: Invalid topic (empty topicArg)')
            return

    if topicType == 'deliveryreport':
        try:
            dr = json.loads(message)
        except:
            funcs.log('Unable to parse delivery report')
            return
        sender = funcs.cleanNumber(dr['source_number'])
        if 'reply_id' in dr:    # A reply, not a delivery report
            senderName = funcs.lookupName(sender)
            reply = dr['content']
            funcs.log(f'Reply received from {senderName}: "{reply}"')
            # Find original message and post reply as a comment
            ts = dr['metadata']['ts']
            if funcs.slackComment(ts, f'{senderName}: {reply}') is None:
                funcs.slackPost(senderName, '-', reply)
        else:                   # Delivery report
            ts = sms.deliveryReport(dr)
            if sms.msgSent(ts):
                if ts is None:
                    funcs.log(f'Message for thread {ts} delivered to {sms.msgRecips(ts)} recipients')
                else:
                    duration = int(time.time() - float(ts))
                    funcs.log(f'Message for thread {ts} delivered to {sms.msgRecips(ts)} recipients in {duration} seconds')
                    if sms.isSlackThread(ts):
                        funcs.slackComment(ts, f'SMS sent to {sms.msgRecips(ts)} recipients in {duration} seconds')

    if topicType == 'smsfrom':
        receivedSms(topicArg, message)
    
    if topicType == 'smsto':
        if 'FROM:' in message:
            msgText = message.split(':')
            sender = msgText[1]
            message = funcs.cleanup(':'.join(msgText[2:]))     # In case of :'s in message
        else:
            sender = 'Internal'
        sendMessage(topicArg, message, sender)

##
##      Main Functions
##

def receivedSms(sender, msg):
    message = funcs.cleanup(msg)
    senderName = funcs.lookupName(sender)
    funcs.log(f'Received SMS from {sender} ({senderName})')
    if funcs.smsIgnore(senderName, message):
        funcs.log('Ignoring this SMS')
        return
    if sender in blockedSenders:
        funcs.log('Ignoring SMS from blocked sender')
        return
    # Determine destination
    dest = 'WOL_Mgmt,WOL_Duty_TLs'
    if senderName == 'Beacon':
        if 'SEZWOL' in msg:
            dest = 'WOL_Mgmt,WOL_Duty_TLs'
        if 'SEZDPT' in msg:
            dest = 'DPT_Mgmt'
    if senderName == 'EWN':
        dest = dest + ',DPT_Mgmt,LEMO'
    if senderName == 'NPWS':
        dest = dest + ',DPT_Mgmt,WOL_Planning,LEMO'
    sendMessage(dest, message, senderName)
 
##  Send a message

def sendMessage(dest, message, sender):
    # Individual SMS destinations
    numbersOnly = re.compile('[0-9,]+$')
    if bool(numbersOnly.match(dest)):
        dests = dest.split(',')
        ts = str(time.time())
        sms.sendMsg(sender, message, ts, False, dests)
        funcs.logMsg(sender, dest, message)
        return
    # Add destinations for some types of messages
    if 'WOL43' in message.upper():
        dest = dest + ',VR_Operators'
    if sender == 'EWN' and 'Heavy Rain' in message:
        dest = dest + ',FR_Operators'
    # Log message
    funcs.log(f'Sending message from {sender} to {dest}')
    if 'SEZWOL' in message or 'SEZDPT' in message or 'ICEMS IAR' in message:
        # Beacon messages are posted to Slack from mystic
        ts = str(time.time())
        slack = False
    else:
        ts = str(funcs.slackPost(sender, dest, message))
        slack = True
        funcs.logMsg(sender, dest, message)
    # Send via Beacon
    for d in dest.split(','):
        if 'Beacon' in d:
            beacon = Beacon()
            sent = beacon.sendMsg(d, message)
            if sent:
                funcs.slackComment(ts, f'Message sent via beacon to {beaconGroups[d]}')
            else:
                funcs.slackComment(ts, f'Warning! Could not send to {beaconGroups[d]} via beacon')
    # Send via SMS
    smsRecips = funcs.smsRecipients(dest)
    numRecips = len(smsRecips)
    msgLen = len(message)
    if numRecips > 0:
        if msgLen < 9:
            funcs.log(f'Not sending message from {sender} via SMS - too short')
            funcs.slackComment(ts, f'Not sending message from {sender} via SMS because it is too short')
            return
        sms.sendMsg(sender, message, ts, slack, smsRecips)
        funcs.log(f'{numRecips} SMS recipients, Thread {ts}')
        
##
##      Main
##

if __name__ == "__main__":
    mClient = mqttSub.Client('smsd')
    mClient.on_connect = mqttConnected
    mClient.on_message = mqttReceived

    try:
        mClient.connect(mqttServer, 1883)
    except Exception as ex:
        funcs.log(f'Couldnt connect to MQTT server {mqttServer}')
        sys.exit(1)
    
    mClient.loop_forever()

