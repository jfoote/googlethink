#!/usr/bin/env python

import os, sys, sqlite3, datetime
from tempfile import NamedTemporaryFile

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
    searches = []
    activity = {}
    query = 'SELECT url, visit_count, last_visit_date FROM moz_places where visit_count > 0 order by last_visit_date asc;'
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1970,1,1) + datetime.timedelta(microseconds=int(entry[2]))

        hr_dt = dt.replace(minute=0, second=0, microsecond=0) 
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
    query = '''
        SELECT urls.url, visits.visit_time FROM urls JOIN visits ON urls.id = visits.url
        ''' 
    searches = []
    activity = {}
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1601,1,1) + datetime.timedelta(microseconds=int(entry[1])) -\
            datetime.timedelta(hours=5) # TODO: fix this properly

        hr_dt = dt.replace(minute=0, second=0, microsecond=0) 
        activity[hr_dt] = activity.get(hr_dt, 0) + 1

        params = get_query_params(entry[0])
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
    return queries, activity

def get_html(queries, activity):

    # TODO: 
    # 0. fix bug: annotations that aren't on hours (data points) aren't displayed
    # 1. zoom on past 7 days
    #   ex: dateWindow: [new Date(2014,12-1,29).getTime(),new Date(2014,12-1,30).getTime()]
    # 2. (in javascript) print queries for zoomed interval below chart [DONE-ish]
    #   see: http://dygraphs.com/tests/callback.html

    # hack: add zereos for 'empty' times to make dygraph look correct
    from dateutil import rrule
    start = activity[0][0]
    end = activity[-1][0]
    q_dict = {dt : ct for dt, ct in activity}
    z_dict = {dt : 0 for dt in  rrule.rrule(rrule.HOURLY, dtstart=start, until=end)}
    z_dict.update(q_dict)
    activity = sorted(z_dict.items())

    # create javascript array of data points
    rows = []
    for dt, ct in activity:
        row = "[%s]" % ", ".join([dt.strftime("new Date(%Y,%m-1,%d,%H)"), str(ct)])
        rows.append(row)
    table = "[%s]" % ",\n".join(rows)

    # create javascript array of annotations
    import json
    annos = []
    for dt, params, browser, profile in queries:
        anno = '{ series: "urls per hour", x: %s, shortText: %s, text: %s }'
        try:
            params = json.dumps(str(params))
        except:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!" #TODO
            continue
        anno = anno % (dt.strftime("new Date(%Y,%m-1,%d,%H,%S).getTime()"), params, params)
        annos.append(anno)
    annos = "[%s]" % ",\n".join(annos)
    annos_js = '''
    g.ready(function() {
        g.setAnnotations(%s);
        });
    '''
    annos_js = annos_js % annos

    # substitute into template
    template = open("res/dygraph_template.html", "rt").read()
    graph_html = template.replace("$JS_DATA_ARRAY", table) 
    graph_html = graph_html.replace("$JS_ANNOTATIONS", annos_js)
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

    c_qs, c_act = get_history("Chrome", "History", chrome_profile_dir, query_chrome_db) 
    ff_qs, ff_act = get_history("Firefox", "places.sqlite", ff_profile_dir, query_firefox_db)

    queries = ff_qs + c_qs
    activity = []
    for hr in c_act.keys() + ff_act.keys():
        activity.append((hr, c_act.get(hr, 0) + ff_act.get(hr, 0)))

    for dt, params, browser, profile in sorted(queries):
        try:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), params.encode()
        except:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!" #TODO

    open("graph.html", "wt").write(get_html(sorted(queries), sorted(activity)))
