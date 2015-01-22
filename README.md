# googlethink

googlethink generates a graph of Google queries from local Chrome and Firefox history. I currently use it to support time tracking as described [in "Why You Probably Don't Need Automatic Time Tracking"](https://foote.pub/TODO) 

![https://foote.pub/images/googlethink.png]

## Graph

Each point on the X axis the point in time that a Google search was conducted. Mousing over the point displays the search term. The Y axis represents the number of URLs that were visited after the search was conducted (FD: I'm not sure how useful that is :). 

## Table

The table below the graph displays all of the searches that were conducted during the displayed interval.

# Installation/usage

```
$ git clone https://github.com/jfoote/googlethink && cd googlethink
$ ./query.py
$ open graph.html # or whatever 
```

## How it works

The visualization is built on [DyGraph](https://dygraph.com) but I continue to tinker with it; as it stands zooming sometimes causes the visualization to flake out, but all of the buttons should work.
