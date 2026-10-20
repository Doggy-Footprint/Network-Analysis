import json,sys
from collections import Counter
out=sys.argv[1]
for name in "nestjs android futurama realworld template".split():
  for g in ("file","symbol"):
    b=json.load(open(f"{out}/base-{name}-{g}.json")); h=json.load(open(f"{out}/head-{name}-{g}.json"))
    bn={n['id']:n for n in b['nodes']}; hn={n['id']:n for n in h['nodes']}
    ch=[]
    for i,n in hn.items():
      o=bn.get(i)
      if o is None: ch.append((i,'NEW NODE')); continue
      if n.get('flags')!=o.get('flags'): ch.append((i,sorted(set(n['flags'])-set(o['flags'])),sorted(set(o['flags'])-set(n['flags']))))
      ob={k:v for k,v in o.items() if k!='flags'}; nb={k:v for k,v in n.items() if k!='flags'}
      if ob!=nb: ch.append((i,'NONFLAG CHANGE'))
    if set(bn)-set(hn): ch.append(('REMOVED',len(set(bn)-set(hn))))
    ek=lambda e:json.dumps(e,sort_keys=True)
    eb=Counter(map(ek,b['edges'])); eh=Counter(map(ek,h['edges']))
    bb=json.load(open(f"{out}/base-{name}-{g}.bottlenecks.json")); hb=json.load(open(f"{out}/head-{name}-{g}.bottlenecks.json"))
    cand=lambda d:Counter(c.get('kind') for c in d.get('candidates',[]))
    print(f"== {name}/{g}: node changes {len(ch)}, edges +{sum((eh-eb).values())} -{sum((eb-eh).values())}, cand base {dict(cand(bb))} head {dict(cand(hb))}, keys same {set(bb)==set(hb)} schema {bb.get('schema')}/{hb.get('schema')}")
    for c in ch[:30]: print("  ",c)
