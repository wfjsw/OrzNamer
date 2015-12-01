#!/usr/bin/env python3
# -*- coding: utf-8 -*-


import os
import re
import time

import flask
from itsdangerous import URLSafeTimedSerializer

AVAIL_LANG = ('zh-cn', 'zh-tw', 'en')
MAX_AGE = 180
# CHANGE THIS
SECRETKEY = b'4\xaf\x05\xcd\xa5Az\xf2\xb57\xc9\x9c\xed\xb1\xfd\x94\xda(\xe0\xcc\x96b\x07*\x89\xa1\xdb*\xd0g\x1d\x13'

app = flask.Flask(__name__)
app.secret_key = SECRETKEY

# From django.utils.translation.trans_real.parse_accept_lang_header
accept_language_re = re.compile(r'''
        ([A-Za-z]{1,8}(?:-[A-Za-z]{1,8})*|\*)       # "en", "en-au", "x-y-z", "*"
        (?:\s*;\s*q=(0(?:\.\d{,3})?|1(?:.0{,3})?))? # Optional "q=1.00", "q=0.8"
        (?:\s*,\s*|$)                               # Multiple accepts per header.
        ''', re.VERBOSE)

def accept_language(lang_string, available):
    """
    Parses the lang_string, which is the body of an HTTP Accept-Language
    header, and returns a list of (lang, q-value), ordered by 'q' values.
    """
    result = {}
    pieces = accept_language_re.split(lang_string)
    if pieces[-1]:
        return None
    for i in range(0, len(pieces) - 1, 3):
        first, lang, priority = pieces[i: i + 3]
        if first:
            return None
        priority = priority and float(priority) or 1.0
        result[lang.lower()] = priority
    return max(available, key=lambda x: result.get(x, 0))

@app.before_request
def before_req():
    flask.g.lang = accept_language(flask.request.headers.get('Accept-Language', ''), AVAIL_LANG)

def verify_token(s):
    serializer = URLSafeTimedSerializer(app.secret_key, 'Orz')
    try:
        return serializer.loads(s, max_age=MAX_AGE)
    except Exception:
        return None

def original_title():
    title = '##Orz 分部喵 - daily.orz.chat'
    return title

def change_title(uid, title):
    pass

def get_template(ua, lang, token, uid, title):
    return ' '.join(map(repr, (ua, lang, token, uid, title)))

@app.route('/api')
def index():
    token = flask.request.args.get('t', '')
    oldtitle = original_title()
    newtitle = flask.request.args.get('n', '')
    uid = verify_token(token)
    if uid and newtitle:
        change_title(uid, newtitle)
        ret = {'ok': True, 'uid': uid, 'title': newtitle}
        return flask.make_response(flask.json.dumps(ret), 200)
    else:
        ret = {'ok': False, 'title': oldtitle}
        return flask.make_response(flask.json.dumps(ret), 403)

@app.route('/generate_204')
def generate_204():
    return flask.Response(status=204)

if __name__ == "__main__":
    app.run(port=5111)