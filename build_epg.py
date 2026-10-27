#!/usr/bin/env python3
"""Download XMLTV EPG, build searchable local SQLite and Gemini-friendly JSON exports."""
import argparse, csv, gzip, io, json, re, sqlite3, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

DEFAULT_URL='https://github.com/ferteque/Curated-M3U-Repository/raw/refs/heads/main/epg6.xml.gz'
SPORTS=re.compile(r'\b(?:sport|football|soccer|premier league|champions league|rugby|cricket|tennis|formula\s*1|\bf1\b|motogp|nba|nfl|nhl|mlb|afl|nrl|ufc|mma|boxing|golf|cycling|olympic|basketball|baseball|hockey|racing|grand prix|wwe|world cup|a-league|super league|europa league|eurosport|espn|bein|sky sports|fox sports|tnt sports|dazn|supersport)\b',re.I)
LIVE=re.compile(r'\b(?:live|en vivo|directo|ao vivo)\b',re.I)

def get_text(el,tag):
    return ' '.join(dict.fromkeys((x.text or '').strip() for x in el.findall(tag) if (x.text or '').strip()))

def date_iso(raw):
    if not raw: return None
    try: return datetime.strptime(raw[:19],'%Y%m%d%H%M%S %z').isoformat()
    except ValueError:
        try: return datetime.strptime(raw[:14],'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).isoformat()
        except ValueError: return raw

def run(source, output):
    output.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(output/'guide.sqlite')
    db.executescript('''DROP TABLE IF EXISTS channels; DROP TABLE IF EXISTS programmes;
    CREATE TABLE channels(id TEXT PRIMARY KEY,name TEXT,logo TEXT,likely_sports INTEGER DEFAULT 0);
    CREATE TABLE programmes(id INTEGER PRIMARY KEY,channel_id TEXT,start TEXT,stop TEXT,title TEXT,description TEXT,category TEXT,likely_sports INTEGER,live_hint INTEGER);
    CREATE INDEX idx_prog_time ON programmes(start);
    CREATE INDEX idx_prog_channel ON programmes(channel_id,start);
    CREATE INDEX idx_prog_title ON programmes(title);''')
    if Path(source).is_file():
        stream=open(source,'rb')
    else:
        req=urllib.request.Request(source,headers={'User-Agent':'Gemini-EPG-Bridge/1.0'})
        stream=urllib.request.urlopen(req,timeout=120)
    with stream:
        buffer=gzip.GzipFile(fileobj=stream) if source.lower().split('?')[0].endswith('.gz') else stream
        root_context=ET.iterparse(buffer,events=('start','end'))
        _,root=next(root_context)
        n=0
        for event,el in root_context:
            if event!='end' or el.tag not in ('channel','programme'): continue
            if el.tag=='channel':
                name=get_text(el,'display-name')
                logo=next((x.get('src','') for x in el.findall('icon')),'')
                sports=int(bool(SPORTS.search(name)))
                db.execute('INSERT OR REPLACE INTO channels VALUES (?,?,?,?)',(el.get('id',''),name,logo,sports))
            else:
                title=get_text(el,'title'); desc=get_text(el,'desc'); cat=get_text(el,'category')
                sports=int(bool(SPORTS.search(' '.join((title,cat)))))
                live=int(bool(LIVE.search(title)))
                db.execute('INSERT INTO programmes(channel_id,start,stop,title,description,category,likely_sports,live_hint) VALUES (?,?,?,?,?,?,?,?)',
                           (el.get('channel',''),date_iso(el.get('start')),date_iso(el.get('stop')),title,desc,cat,sports,live))
            n+=1
            if n%25000==0: db.commit()
            el.clear();root.clear()
    db.commit()
    db.execute('UPDATE programmes SET likely_sports=1 WHERE channel_id IN (SELECT id FROM channels WHERE likely_sports=1)')
    db.commit()
    db.row_factory=sqlite3.Row
    channels=[dict(x) for x in db.execute('SELECT * FROM channels ORDER BY name,id')]
    with open(output/'channels.json','w',encoding='utf-8') as f:json.dump(channels,f,ensure_ascii=False,separators=(',',':'))
    with open(output/'channels.csv','w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['id','name','logo','likely_sports']);w.writeheader();w.writerows(channels)
    # Export only current and future sport-candidate broadcasts; tune the keyword filter in SPORTS above.
    now=datetime.now(timezone.utc).isoformat()
    query='''SELECT p.channel_id,c.name AS channel_name,p.start,p.stop,p.title,p.description,p.category,p.live_hint
             FROM programmes p LEFT JOIN channels c ON c.id=p.channel_id
             WHERE p.likely_sports=1 AND p.stop>=? ORDER BY p.start LIMIT 100000'''
    sports=[dict(x) for x in db.execute(query,(now,))]
    with open(output/'sports_events.json','w',encoding='utf-8') as f:json.dump(sports,f,ensure_ascii=False,separators=(',',':'))
    stats={'generated_utc':datetime.now(timezone.utc).isoformat(),'source':source,'channel_count':len(channels),
           'programme_count':db.execute('SELECT COUNT(*) FROM programmes').fetchone()[0],
           'future_sports_candidates':len(sports),'note':'Sport and live labels are heuristic; verify title and broadcast before adding calendar events.'}
    (output/'status.json').write_text(json.dumps(stats,indent=2),encoding='utf-8')
    db.close();print(json.dumps(stats,indent=2))

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',default=DEFAULT_URL,help='Raw URL or local .xml.gz file')
    parser.add_argument('--output',default='data',help='Output directory')
    args=parser.parse_args();run(args.source,Path(args.output))
