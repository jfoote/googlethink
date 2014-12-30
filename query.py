#!/usr/bin/env python

import os, sys, sqlite3, datetime, json
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
    query = 'SELECT url, visit_count, last_visit_date FROM moz_places where visit_count > 0 order by last_visit_date asc;'
    con = sqlite3.connect(path)
    for entry in con.execute(query).fetchall():
        dt = datetime.datetime(1970,1,1) + datetime.timedelta(microseconds=int(entry[2]))
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

def get_html(queries, history):

    # TODO: 
    # 0. fix bug: annotations that aren't on hours (data points) aren't displayed
    # 1. zoom on past 7 days
    #   ex: dateWindow: [new Date(2014,12-1,29).getTime(),new Date(2014,12-1,30).getTime()]
    # 2. (in javascript) print queries for zoomed interval below chart [DONE-ish]
    #   see: http://dygraphs.com/tests/callback.html

    '''
    # hack: add zereos for 'empty' times to make dygraph look correct
    from dateutil import rrule
    start = activity[0][0]
    end = activity[-1][0]
    q_dict = {dt : ct for dt, ct in activity}
    z_dict = {dt : 0 for dt in  rrule.rrule(rrule.HOURLY, dtstart=start, until=end)}
    z_dict.update(q_dict)
    activity = sorted(z_dict.items())
    '''

    # create javascript arrays of dygraph data points and raw data, respectively
    data_rows = []
    raw_rows = []
    last = None
    for dt, entry, browser, profile_id, ct, params in history:
        if last and last > dt:
            print last, dt
            import pdb; pdb.set_trace()
        last = dt
        row = "[%s]" % ", ".join([dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S)"), str(ct)])
        data_rows.append(row)
        jsons = [json.dumps(i) for i in [entry, browser, profile_id, ct, params]]
        row = "[%s]" % ", ".join([dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S)")] + jsons)
        raw_rows.append(row)
    data = "[%s]" % ",\n".join(data_rows)
    raw = "[%s]" % ",\n".join(raw_rows)

    # create javascript array of annotations
    annos = []
    for dt, params in queries:
        anno = '{ series: "urls per hour", x: %s, shortText: %s, text: %s }'
        try:
            params = json.dumps(str(params))
        except:
            print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!" #TODO
            continue
        #anno = anno % (dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S).getTime()"), params, params)
        anno = anno % (dt.strftime("new Date(%Y,%m-1,%d,%H,%M,%S).getTime()"), '"G"', params)
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
    graph_html = template.replace("$JS_DATA_ARRAY", data) 
    graph_html = graph_html.replace("$JS_ANNOTATIONS", annos_js)
    graph_html = graph_html.replace("$JS_RAW_DATA", raw)
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
    history.sort(key=lambda h: h[0])

    counts = {}
    for dt, entry, browser, profile_id in history:
        hr = dt.replace(minute=0, second=0, microsecond=0)
        counts[hr] = counts.get(hr, 0) + 1

    hhistory = []
    last_query = None
    queries = []
    for dt, entry, browser, profile_id in history:
        params = get_query_params(entry)
        if params:
            last_query = params
            queries.append((dt, params))
            try:
                print dt.strftime("%Y-%m-%d %H:%M:%S"), params.encode()
            except:
                print dt.strftime("%Y-%m-%d %H:%M:%S"), "ERROR!"
        hr = dt.replace(minute=0, second=0, microsecond=0)
        hhistory.append((dt, entry, browser, profile_id, counts[hr], last_query))

    open("graph.html", "wt").write(get_html(queries, hhistory))
