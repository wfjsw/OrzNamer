#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import time
import json
import socket
import logging
import requests
import threading
import http.server
import socketserver
import urllib.parse

import tgcli
from itsdangerous import URLSafeTimedSerializer

RE_INVALID = re.compile("[\000-\037\t\r\x0b\x0c\ufeff]")

logging.basicConfig(stream=sys.stderr, format='%(asctime)s [%(levelname)s] %(message)s', level=logging.DEBUG if sys.argv[-1] == '-d' else logging.INFO)

class AttrDict(dict):
    def __init__(self, *args, **kwargs):
        super(AttrDict, self).__init__(*args, **kwargs)
        self.__dict__ = self

# API bot

HSession = requests.Session()

class BotAPIFailed(Exception):
    pass

def bot_api(method, **params):
    for att in range(3):
        try:
            req = HSession.get(('https://api.telegram.org/bot%s/' % CFG.apitoken) + method, params=params, timeout=45)
            retjson = req.content
            ret = json.loads(retjson.decode('utf-8'))
            break
        except Exception as ex:
            if att < 1:
                time.sleep((att+1) * 2)
            else:
                raise ex
    if not ret['ok']:
        raise BotAPIFailed(repr(ret))
    return ret['result']

def getupdates():
    global STATE
    while 1:
        try:
            updates = bot_api('getUpdates', offset=STATE['offset'], timeout=10)
        except Exception as ex:
            logging.exception('Get updates failed.')
            continue
        if updates:
            logging.debug('Messages coming.')
            STATE['offset'] = updates[-1]["update_id"] + 1
            for upd in updates:
                processmsg(upd)
        time.sleep(.2)

def processmsg(d):
    logging.debug('Msg arrived: %r' % d)
    uid = d['update_id']
    if 'message' in d:
        msg = d['message']
        if msg['chat']['type'] == 'private' and msg.get('text', '').startswith('/t'):
            logging.info(bot_api('sendMessage', chat_id=msg['chat']['id'], text=CFG.url + get_token(msg['from']['id'])))

# Cli bot

def get_members():
    global CFG
    # To ensure the id is valid
    TGCLI.cmd_dialog_list()
    peername = '%s#id%d' % (CFG.grouptype, CFG.groupid)
    if CFG.grouptype == 'channel':
        items = TGCLI.cmd_channel_get_members(peername, 100)
        for item in items:
            STATE.members[str(item['peer_id'])] = item
        dcount = 100
        while items:
            items = TGCLI.cmd_channel_get_members(peername, 100, dcount)
            for item in items:
                STATE.members[str(item['peer_id'])] = item
            dcount += 100
        STATE.title = TGCLI.cmd_channel_info(peername)['title']
    else:
        obj = TGCLI.cmd_chat_info(peername)
        STATE.title = obj['title']
        items = obj['members']
        for item in items:
            STATE.members[str(item['peer_id'])] = item

def handle_update(obj):
    global STATE
    try:
        if (obj.get('event') == 'message' and obj['to']['peer_id'] == CFG.groupid and obj['to']['peer_type'] == CFG.grouptype):
            STATE.members[str(obj['from']['peer_id'])] = obj['from']
            STATE.title = obj['to']['title']
    except Exception:
        logging.exception("can't handle message event")

# HTTP Server

class ThreadingHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    def server_bind(self, *args, **kwargs):
        super().server_bind(*args, **kwargs)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

class HTTPHandler(http.server.BaseHTTPRequestHandler):

    def send_response(self, code, message=None):
        self.send_response_only(code, message)
        self.send_header('Server', self.version_string())
        self.send_header('Date', self.date_time_string())

    def log_message(self, format, *args):
        logging.info('%s - - [%s] %s "%s" "%s"' % (
            self.headers.get('X-Forwarded-For', self.address_string()),
            self.log_date_time_string(), format % args, self.headers.get('Referer', '-'), self.headers.get('User-Agent', '-')))

    def log_date_time_string(self):
        """Return the current time formatted for logging."""
        lt = time.localtime(time.time())
        s = time.strftime('%d/%%3s/%Y:%H:%M:%S %z', lt) % self.monthname[lt[1]]
        return s

    def title_api(self, path):
        path = urllib.parse.unquote_plus(path, errors='ignore')
        qs = path.split('?', 1)
        path = qs[0].split('#', 1)[0].rstrip()
        if path != '/title':
            return 404, '404 Not Found'
        if len(qs) > 1:
            query = urllib.parse.parse_qs(qs[1])
        else:
            query = {}
        if 't' in query:
            if 'n' in query:
                newtitle = query['n'][0]
                code, ret = change_title(query['t'][0], newtitle)
                if code == 200:
                    ret['title'] = newtitle
                elif code != 403:
                    ret['title'] = STATE.title
                return code, json.dumps(ret)
            else:
                uid = verify_token(query['t'][0])
                if uid:
                    return 200, json.dumps({'title': STATE.title})
                else:
                    return 403, json.dumps({'error': 'invalid token'})
        else:
            return 403, json.dumps({'error': 'token not specified'})

    def do_GET(self):
        code, text = self.title_api(self.path)
        text = text.encode('utf-8')
        self.send_response(code)
        length = len(text)
        self.log_request(code, length)
        self.send_header('Content-Length', length)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(text)

# Processing

def token_gc():
    for uid, gentime in tuple(STATE.tokens.items()):
        if time.time() - gentime > CFG.tokenexpire:
            del STATE.tokens[str(uid)]

def get_token(uid):
    serializer = URLSafeTimedSerializer(CFG.secretkey, 'Orz')
    STATE.tokens[str(uid)] = time.time()
    return serializer.dumps(uid)

def verify_token(token):
    serializer = URLSafeTimedSerializer(CFG.secretkey, 'Orz')
    try:
        uid = serializer.loads(token, max_age=CFG.tokenexpire)
        if time.time() - STATE.tokens[str(uid)] > CFG.tokenexpire:
            return False
    except Exception:
        logging.exception('token failed')
        return False
    return uid

def change_title(token, title):
    uid = verify_token(token)
    if uid is False:
        return 403, {'error': 'invalid token'}
    ret = TGCLI.cmd_rename_channel('%s#id%d' % (CFG.grouptype, CFG.groupid), CFG.prefix + title)
    if ret['result'] == 'SUCCESS':
        bot_api('sendMessage', chat_id=CFG.apigroupid, text='@%s 修改了群组名称。' % STATE.members[str(uid)]['username'])
        del STATE.tokens[str(uid)]
        STATE.title = CFG.prefix + title
        return 200, ret
    else:
        return 406, ret

def load_config():
    cfg = AttrDict(json.load(open('config.json', encoding='utf-8')))
    if os.path.isfile('state.json'):
        state = AttrDict(json.load(open('state.json', encoding='utf-8')))
    else:
        state = AttrDict({'offset': 0, 'members': {}, 'tokens': {}})
    return cfg, state

def save_config():
    json.dump(STATE, open('state.json', 'w'), indent=1)

def run(server_class=ThreadingHTTPServer,
        handler_class=HTTPHandler):
    server_address = (CFG.serverip, CFG.serverport)
    httpd = server_class(server_address, handler_class)
    httpd.serve_forever()

if __name__ == '__main__':
    CFG, STATE = load_config()
    TGCLI = tgcli.TelegramCliInterface(CFG.tgclibin)
    TGCLI.ready.wait()
    try:
        get_members()

        apithr = threading.Thread(target=getupdates)
        apithr.daemon = True
        apithr.start()

        run()
    finally:
        save_config()
        TGCLI.close()
