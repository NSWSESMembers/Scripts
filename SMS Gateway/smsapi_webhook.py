#!/usr/bin/python3
from flask import Flask, request
from OpenSSL import SSL
import os
import json
import paho.mqtt.publish as mqttPub

mqttAuth = {'username': 'REDACTED', 'password': 'REDACTED'}

app = Flask(__name__)

@app.route('/', methods=['POST','GET'])
def index():
    if request.method == 'GET':
        return '<p>Nothing to see here - move along</p>'
    if request.method == 'POST':
        payload = request.get_json()
        if 'Test' in payload:
            mqttPub.single('/test/test', json.dumps(payload), qos=1, hostname='localhost', auth=mqttAuth)
        if 'delivery_report_id' in payload:
            mqttPub.single('/smsapi/deliveryreport', json.dumps(payload), qos=1, hostname='localhost', auth=mqttAuth)
            print('Delivery report for ' + payload['source_number'] + ' received')
        return '{"success":"true"}'

if __name__ == "__main__":   
    app.run(host='0.0.0.0', port=8443, threaded=True)
