idid
====
# Re-design:

## Goal
- Graph data points are queries
    - x is date of query
    - y is number of URLs browsed after query
- urldiv below graph shows
    - URLs visited during displayed days (see drawCallback + g.xAxisRange())
- highlightdiv below graph shows
    - query terms, browser, profile ID
```
[   GRAPH   ]
highlight
data
```

## Design

### Python must store
- history_by_day: a dict of url, entry, params, ct, etc. keyed by javascript date
- data_table: a table of (dt, url_count) for each time a new search was executed 
- raw_data: a mirror table to data_table, but includes params, browser, profile_id, etc. 

### Javascript
- highlightcallback looks up row in raw_data to display it
- drawCallback does a for() loop over days in g.xAxisRange and displays keyed data from history_by_day, if any exists
    - can "truncate" supplied start/end times using math on milliseconds, if necessary
