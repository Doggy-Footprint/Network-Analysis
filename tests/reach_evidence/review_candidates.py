import json, subprocess, sys, re
from pathlib import Path
from fixtures.registry import fixture_root
from language_analyzers.core.flags import path_flags
CMDS={'futuramaapi':['-l','python'],'fastapi-realworld':['-l','python'],'android-nowinandroid':['-l','kotlin'],'typescript-nestjs-realworld':['-l','typescript','-f','nestjs']}
S=Path(sys.argv[1]); out=[]
SRC=('.py','.ts','.tsx','.js','.kt')
for name,args in CMDS.items():
    root=fixture_root(name); b=S/f'bn_{name}.json'; h=S/f'rv_{name}.html'
    subprocess.run([sys.executable,'-m','code_analyzer',*args,str(root),'--bottlenecks',str(b),'-o',str(h),'--json'],check=True,capture_output=True)
    arch=json.loads(h.with_suffix('.json').read_text()); rep=json.loads(b.read_text())
    edges=arch['edges']
    files=[p for p in (n['metadata'].get('file_path') for n in arch['nodes'] if n['id'].startswith('file:')) if p]
    def cat(p):
        f=path_flags(p); return 'vendored' if 'vendored' in f else 'generated' if 'generated' in f else 'test' if 'test' in f else 'production'
    tests=[p for p in files if cat(p)=='test']; prods=[p for p in files if cat(p)=='production' and p.endswith(SRC)]
    text={p:(root/p).read_text(errors='ignore') for p in tests+prods}
    out.append(f'\n## {name} (`{" ".join(args)}`)\n')
    out.append('| kind | target | product evidence | independent text check | consistent |\n| --- | --- | --- | --- | --- |')
    for c in sorted((c for c in rep['candidates'] if c['kind'] in ('untested_hub','isolated_node')),key=lambda c:(c['kind'],c['target'])):
        t=c['target']; path=t[5:]; stem=Path(path).stem
        if c['kind']=='untested_hub':
            inc=[e for e in edges if e['relation']=='TESTS' and (e['to_id']==t or t in (e.get('candidates') or []))]
            conf=[e for e in inc if e['resolution'] in ('exact','unique_name')]
            mention=[p for p in tests if re.search(r'\b'+re.escape(stem)+r'\b',text[p])]
            ev=f"rank {c['metrics']['pagerank_rank']}, confirmed TESTS {len(conf)}, uncertain {c['metrics']['uncertain_test_edge_count']}"
            chk=f"test files mentioning `{stem}`: {len(mention)}" + (f" ({', '.join(mention[:2])})" if mention else '')
            ok='yes' if not conf else 'NO'
            if mention and not inc: ok+=' (analyzer emits no edge from these test files: F11)' if path.endswith(('.ts','.tsx','.js')) else ' (name mention without resolved edge)'
        else:
            touch=[e for e in edges if t in (e['from_id'],e['to_id'],*(e.get('candidates') or []))]
            others=[e for e in touch if e['confidence'] in ('static_certain','static_inferred') and e['resolution'] in ('exact','unique_name') and {e['from_id'],e['to_id']}-{t} and all(x.startswith('file:') and cat(x[5:])=='production' for x in {e['from_id'],e['to_id']}-{t})]
            mention=[p for p in prods if p!=path and re.search(r'\b'+re.escape(stem)+r'\b',text[p])]
            ev=f"{c['metrics']['line_count']} lines, edges touching {len(touch)} ({', '.join(sorted({e['relation']+'/'+e['confidence'] for e in touch})) or 'none'}), static production connections {len(others)}"
            chk=f"other production files mentioning `{stem}`: {len(mention)}" + (f" ({', '.join(mention[:2])})" if mention else '')
            ok='yes' if not others else 'NO'
        out.append(f"| {c['kind']} | `{path}` | {ev} | {chk} | {ok} |")
print('\n'.join(out))
