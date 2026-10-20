import ast, random, subprocess, sys, re, json
BASE="cf0cf4446106f44026dc40d00ba09df977d61ecc"
FILES=["bottlenecks/core.py","analysis/graph_metrics.py","analysis/edge_weights.py","analysis/file_graph.py","language_analyzers/python/graph.py","language_analyzers/typescript/analyzer.py","language_analyzers/kotlin/analyzer.py","language_analyzers/kotlin/ast.py","report/bottlenecks/generate.py"]
def changed(f):
    out=subprocess.run(["git","diff","-U0",BASE,"--",f],capture_output=True,text=True).stdout
    lines=set()
    for m in re.finditer(r"^@@ -\S+ \+(\d+)(?:,(\d+))? @@",out,re.M):
        s,n=int(m.group(1)),int(m.group(2) or 1); lines.update(range(s,s+n))
    return lines
CMP={ast.Lt:ast.LtE,ast.LtE:ast.Lt,ast.Gt:ast.GtE,ast.GtE:ast.Gt,ast.Eq:ast.NotEq,ast.NotEq:ast.Eq,ast.In:ast.NotIn,ast.NotIn:ast.In}
cands=[]
for f in FILES:
    src=open(f).read(); tree=ast.parse(src); L=changed(f)
    for node in ast.walk(tree):
        ln=getattr(node,"lineno",None)
        if ln not in L: continue
        if isinstance(node,ast.Compare):
            for i,op in enumerate(node.ops):
                if type(op) in CMP: cands.append((f,ln,"cmp",id(node),i))
        elif isinstance(node,ast.BoolOp): cands.append((f,ln,"bool",id(node),0))
        elif isinstance(node,ast.Constant) and isinstance(node.value,int) and not isinstance(node.value,bool): cands.append((f,ln,"const",id(node),0))
        elif isinstance(node,ast.If): cands.append((f,ln,"negate",id(node),0))
        elif isinstance(node,ast.Constant) and isinstance(node.value,str) and len(node.value)<40: cands.append((f,ln,"str",id(node),0))
        elif isinstance(node,ast.Set) and len(node.elts)>1:
            for i in range(len(node.elts)): cands.append((f,ln,"setdrop",id(node),i))
rnd=random.Random(20261020)
sample=rnd.sample(cands,min(30,len(cands)))
def apply(f,ln,kind,nid,i):
    src=open(f).read(); tree=ast.parse(src)
    # re-find node by walk order identity: match by (lineno, kind, position index)
    targets=[n for n in ast.walk(tree) if getattr(n,"lineno",None)==ln]
    for n in targets:
        if kind=="cmp" and isinstance(n,ast.Compare) and i<len(n.ops) and type(n.ops[i]) in CMP: n.ops[i]=CMP[type(n.ops[i])](); return ast.unparse(tree)
        if kind=="bool" and isinstance(n,ast.BoolOp): n.op=ast.Or() if isinstance(n.op,ast.And) else ast.And(); return ast.unparse(tree)
        if kind=="const" and isinstance(n,ast.Constant) and isinstance(n.value,int) and not isinstance(n.value,bool): n.value+=1; return ast.unparse(tree)
        if kind=="negate" and isinstance(n,ast.If): n.test=ast.UnaryOp(ast.Not(),n.test); return ast.unparse(tree)
        if kind=="str" and isinstance(n,ast.Constant) and isinstance(n.value,str) and len(n.value)<40: n.value=n.value+"_x"; return ast.unparse(tree)
        if kind=="setdrop" and isinstance(n,ast.Set) and len(n.elts)>i: del n.elts[i]; return ast.unparse(tree)
    return None
cmd=["uv","run","-q","--with-requirements","requirements-dev.txt","python","-m","pytest","-q","-p","no:cacheprovider","-x","tests/test_signal_defects.py"]
results=[]
for k,(f,ln,kind,nid,i) in enumerate(sample):
    new=apply(f,ln,kind,nid,i)
    if new is None: results.append(dict(id=k,file=f,line=ln,kind=kind,result="inconclusive")); continue
    subprocess.run(["python3",".harness/bin/seed.py","backup",f],check=True,capture_output=True)
    open(f,"w").write(new)
    try:
        r=subprocess.run(cmd,capture_output=True,text=True,timeout=1200)
        res="killed" if r.returncode==1 else "survived" if r.returncode==0 else "inconclusive"
    except subprocess.TimeoutExpired: res="inconclusive"
    finally:
        rr=subprocess.run(["python3",".harness/bin/seed.py","restore"],capture_output=True,text=True)
        if rr.returncode: print("RESTORE FAILED"); sys.exit(2)
    results.append(dict(id=k,file=f,line=ln,kind=kind,pos=i,result=res))
json.dump(results,open(sys.argv[1],"w"),indent=1)
from collections import Counter; print(len(cands),Counter(r["result"] for r in results))
for r in results:
    if r["result"]!="killed": print(r)
