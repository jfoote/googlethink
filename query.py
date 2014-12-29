#!/usr/bin/env python

import os, sys, sqlite3, datetime
from tempfile import NamedTemporaryFile
from copy import deepcopy

def get_query_params(url):
    from urlparse import urlparse, parse_qs
    parsed = urlparse(url)
    # google
    #str_len = len("google.com")
    #if parsed.netloc and len(parsed.netloc) >= str_len and parsed.netloc[-str_len:] == "google.com":
    if parsed.netloc and "www.google.com" in parsed.netloc or "encrypted.google.com" in parsed.netloc: # TODO: regex to match line ending
        if "#" in url:
            q_str = url.split("#")[-1] # google uses 'q=' that comes after #; parsed.query strips this part
        else:
            q_str = parsed.query
        params = parse_qs(q_str)
        if "q" in params.keys():
            #return params["q"][0].replace("+", " ")
            return " ".join([q.replace("+", " ") for q in params["q"]])
    return None

def query_firefox_db(path):
    searches = []
    activity = {}
    query = 'SELECT url, visit_count, last_visit_date FROM moz_places where visit_count > 0 order by last_visit_date asc;'
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1970,1,1) + datetime.timedelta(microseconds=int(entry[2]))
        hr_dt = deepcopy(dt)
        hr_dt.replace(hour=0, minute=0, second=0, microsecond=0) 
        activity[hr_dt] = activity.get(hr_dt, 0) + 1

        params = get_query_params(entry[0])
        if params:
            searches.append((dt, params))
    return searches, activity

def query_chrome_db(path):
    query = '''
        SELECT urls.id, urls.url, urls.title, urls.visit_count, urls.typed_count, urls.last_visit_time,
        urls.hidden, urls.favicon_id, visits.visit_time, visits.from_visit, visits.visit_duration,
        visits.transition, visit_source.source
        FROM urls JOIN visits ON urls.id = visits.url LEFT JOIN visit_source ON visits.id = visit_source.id
        ''' 
    searches = []
    activity = {}
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(entry[5])) -\
            datetime.timedelta(hours=5) # TODO: fix this properly

        hr_dt = deepcopy(dt)
        hr_dt.replace(hour=0, minute=0, second=0, microsecond=0) 
        activity[hr_dt] = activity.get(hr_dt, 0) + 1

        params = get_query_params(entry[1])
        if params:
            searches.append((dt, params))
    return searches, activity

def get_history(browser, db_name, profile_dir, query_func):
    queries = []
    activity = {}
    for dirpath, dirnames, filenames in os.walk(profile_dir):
        if db_name not in filenames:
            continue

        path = os.path.join(dirpath, db_name)
        profile_id = os.path.basename(dirpath)
 
        # poor man's read-only mode since python2 doesn't support it
        try:
            queries_i, act_i = query_func(path)
            for hr, ct in act_i.iteritems(): # merge activity into histogram
                activity[hr] = activity.get(hr, 0) + ct
            for dt, params in queries_i: # append queries
                queries.append((dt, params, browser, profile_id))
        except sqlite3.OperationalError:
            with NamedTemporaryFile() as fp:
                fp.write(open(path, "rb").read())
                queries_i, act_i = query_func(fp.name)
                for hr, ct in act_i.iteritems(): # merge activity into histogram
                    activity[hr] = activity.get(hr, 0) + ct
                for dt, params in queries_i:
                    queries.append((dt, params, browser, profile_id))
    return queries


def get_chrome_history(profile_dir):
    queries = []
    activity = {}
    for dirpath, dirnames, filenames in os.walk(profile_dir):
        if "History" not in filenames:
            continue

        path = os.path.join(dirpath, "History")
        profile_id = os.path.basename(dirpath)
 
        # poor man's read-only mode since python2 doesn't support it
        try:
            queries_i, act_i = query_chrome_db(path)
            for hr, ct in act_i.iteritems(): # merge activity into histogram
                activity[hr] = activity.get(hr, 0) + ct
            for dt, params in queries_i: # append queries
                queries.append((dt, params, "Chrome", profile_id))
        except sqlite3.OperationalError:
            with NamedTemporaryFile() as fp:
                fp.write(open(path, "rb").read())
                queries_i, act_i = query_chrome_db(fp.name)
                for hr, ct in act_i.iteritems(): # merge activity into histogram
                    activity[hr] = activity.get(hr, 0) + ct
                for dt, params in queries_i:
                    queries.append((dt, params, "Chrome", profile_id))
    return queries

if __name__ == "__main__":
    # TODO: add CLI
    if "darwin" in sys.platform.lower():
        ff_profile_dir = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        chrome_profile_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome/")
    else:
        # TODO: make this more flexible and specific
        ff_profile_dir = os.path.expanduser("~")
        chrome_profile_dir = os.path.expanduser("~")

    #queries = get_chrome_history(chrome_profile_dir) + get_firefox_history(ff_profile_dir)
    queries = get_history("Chrome", "History", chrome_profile_dir, query_chrome_db) + \
            get_history("Firefox", "places.sqlite", ff_profile_dir, query_firefox_db)
    for dt, params, browser, profile in sorted(queries):
        try:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), params.encode()
        except:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!" #TODO
