#!/usr/bin/env python

import os, sys, sqlite3, datetime, json
from tempfile import NamedTemporaryFile
from datetime import timedelta

def get_query_params(url):
    from urlparse import urlparse, parse_qs
    parsed = urlparse(url)
    # google
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
    query = 'SELECT url, visit_count, last_visit_date FROM moz_places where visit_count > 0 order by last_visit_date asc;'
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1970,1,1) + datetime.timedelta(microseconds=int(entry[2])) -\
                timedelta(hours=5) # TODO: fix this properly
        yield dt, entry[0]

def query_chrome_db(path):
    query = '''
        SELECT urls.url, visits.visit_time FROM urls JOIN visits ON urls.id = visits.url
        ''' 
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(entry[1])) -\
            datetime.timedelta(hours=5) # TODO: fix this properly

        yield dt, entry[0]

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
            for dt, entry in query_func(path):
                yield dt, entry , browser, profile_id
        except sqlite3.OperationalError:
            with NamedTemporaryFile() as fp:
                fp.write(open(path, "rb").read())
                for dt, entry in query_func(fp.name):
                    yield dt, entry , browser, profile_id

#def get_html(queries, history):
def get_html(queries, raw, by_day):

    # create javascript arrays of dygraph data points and raw data, respectively
    data_rows_js = []
    raw_rows_js = []
    for dt, ct, url, browser, profile_id, last_params in raw:
        row_js = "[%s]" % ", ".join([dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S)"), str(ct)])
        data_rows_js.append(row_js)
        jsons = [json.dumps(i) for i in [ct, url, browser, profile_id, last_params]]
        row_js = "[%s]" % ", ".join([dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S)")] + jsons)
        raw_rows_js.append(row_js)
    data_js = "[%s]" % ",\n".join(data_rows_js)
    raw_js = "[%s]" % ",\n".join(raw_rows_js)

    # create javascript dictionary for highlight data
    # dates will be strings, not dates 
    by_str_day = {}
    for day_dt, entries in by_day.iteritems():
        str_day = day_dt.strftime("%Y-%m-%d") 
        str_entries = []
        for entry in entries:
            dt = entry[0]
            str_dt = dt.strftime("%Y-%m-%d %H:%M:%S")
            str_entry = [str_dt] + entry[1:] 
            str_entries.append(str_entry)

        by_str_day[str_day] = str_entries
    by_day_js = json.dumps(by_str_day, indent=4)

    zoom_end = sorted(by_day.keys())[-1] + timedelta(days=1)
    zoom_end_js = zoom_end.strftime("new Date(%Y,%m-1,%d)")
    zoom_start_day = zoom_end - timedelta(days=1)
    zoom_start_day_js = zoom_start_day.strftime("new Date(%Y,%m-1,%d)")
    zoom_start_two_days = zoom_end - timedelta(days=2)
    zoom_start_two_days_js = zoom_start_two_days.strftime("new Date(%Y,%m-1,%d)")
    zoom_start_week = zoom_end - timedelta(days=7)
    zoom_start_week_js = zoom_start_week.strftime("new Date(%Y,%m-1,%d)")
    zoom_start_month = zoom_end - timedelta(days=31)
    zoom_start_month_js = zoom_start_month.strftime("new Date(%Y,%m-1,%d)")

    # substitute into template
    template = open("res/dygraph_template.html", "rt").read()
    graph_html = template.replace("$JS_DATA_ARRAY", data_js) 
    graph_html = graph_html.replace("$JS_BY_DAY", by_day_js)
    graph_html = graph_html.replace("$JS_RAW_DATA", raw_js)
    graph_html = graph_html.replace("$JS_ZOOM_WEEK_MIN", zoom_start_week_js)
    graph_html = graph_html.replace("$JS_ZOOM_DAY_MIN", zoom_start_day_js)
    graph_html = graph_html.replace("$JS_ZOOM_TWO_DAYS_MIN", zoom_start_two_days_js)
    graph_html = graph_html.replace("$JS_ZOOM_MONTH_MIN", zoom_start_month_js)
    graph_html = graph_html.replace("$JS_ZOOM_MAX", zoom_end_js)
    return graph_html

if __name__ == "__main__":
    # TODO: add CLI
    if "darwin" in sys.platform.lower():
        ff_profile_dir = os.path.expanduser("~/Library/Application Support/Firefox/Profiles")
        chrome_profile_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome/")
    else:
        # TODO: make this more flexible and specific
        ff_profile_dir = os.path.expanduser("~")
        chrome_profile_dir = os.path.expanduser("~")

    # yield dt, entry , browser, profile_id
    history = [h for h in get_history("Chrome", "History", chrome_profile_dir, query_chrome_db)] +\
            [h for h in get_history("Firefox", "places.sqlite", ff_profile_dir, query_firefox_db)]
    history.sort()

    queries = [] 
    raw = []
    by_day = {}
    last_info = None
    ct = 0
    for dt, url, browser, profile_id in history:
        # if this is a search query, record it to data & raw tables
        params = get_query_params(url)
        if params:
            if last_info:
                queries.append((last_info[0], ct))
                raw.append((last_info[0], ct, last_info[1], last_info[2], last_info[3], last_info[4]))

                # store query into to by_day dict
                day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
                by_day[day] = by_day.get(day, []) + [[dt, last_info[4], last_info[2], last_info[3]]]

            last_info = dt, url, browser, profile_id, params
            ct = 0

            # print search query info to stdout
            try:
                print dt.strftime("%Y-%m-%d %H:%M:%S"), params.encode()
            except:
                print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!"
        ct += 1

        
    # store info for final search query
    queries.append((last_info[0], ct))
    raw.append((last_info[0], ct, last_info[1], last_info[2], last_info[3], last_info[4]))
    day = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    by_day[day] = by_day.get(day, []) + [[dt, last_info[4], last_info[2], last_info[3]]]
    


    open("graph.html", "wt").write(get_html(queries, raw, by_day))
