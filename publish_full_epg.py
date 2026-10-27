#!/usr/bin/env python3
"""Export ALL XMLTV programme rows from the existing SQLite index as date-sharded JSON."""
import json,sqlite3,gzip
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

DB=Path('data/guide.sqlite')
OUT=Path('docs/full')
SYDNEY=ZoneInfo('Australia/Sydney')

def main():
    db=sqlite3.connect(DB)
    db.row_factory=sqlite3.Row
    OUT.mkdir(parents=True,exist_ok=True)
    for old in OUT.glob('*.json*'):old.unlink()
    dates=defaultdict(list)
    bad=0
    for r in db.execute('''SELECT p.channel_id,p.start,p.stop,p.title,p.category,p.description,c.name AS channel_name
                         FROM programmes p LEFT JOIN channels c ON c.id=p.channel_id ORDER BY p.start'''):
        try:
            d=datetime.fromisoformat(r['start']).astimezone(SYDNEY).date().isoformat()
        except (ValueError,TypeError):
            bad+=1;continue
        # Compact arrays reduce repository size. Fields described in meta.json.
        dates[d].append([r['start'],r['stop'],r['channel_name'] or r['channel_id'],r['title'],r['channel_id'],r['category'],(r['description'] or '')[:180]])
    for d,items in dates.items():
        with gzip.open(OUT/(d+'.json.gz'),'wt',encoding='utf-8',compresslevel=6) as f:
            json.dump(items,f,ensure_ascii=False,separators=(',',':'))
    manifest={'dates':sorted(dates),'counts':{k:len(v) for k,v in dates.items()},'fields':['start','stop','channel_name','title','channel_id','category','description_excerpt'], 'timezone':'Australia/Sydney','invalid_start_rows':bad}
    (OUT/'meta.json').write_text(json.dumps(manifest,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print('Exported',sum(map(len,dates.values())),'programmes across',len(dates),'dates; bad:',bad)
if __name__=='__main__':main()
