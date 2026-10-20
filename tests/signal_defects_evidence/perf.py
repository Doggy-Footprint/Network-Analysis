"""Q4 wall time: file-mode --bottlenecks, base worktree vs HEAD, interleaved base/head x3, median. Usage: perf.py <scratch dir containing basewt/>"""
import subprocess, sys, time, statistics, os
S=sys.argv[1]; FX='/home/user/Network-Analysis/.fixtures'
targets=[("android","kotlin",f"{FX}/android-nowinandroid"),("nestjs","typescript",f"{FX}/typescript-nestjs-realworld"),("self","python",f"{S}/basewt")]
trees={"base":f"{S}/basewt","head":"/home/user/Network-Analysis"}
res={}
for name,lang,path in targets:
    for tree in ("base","head","base","head","base","head"):
        t=time.perf_counter()
        subprocess.run([sys.executable,"-m","code_analyzer","-l",lang,path,"--granularity","file","--bottlenecks",f"{S}/perf.json","-o",f"{S}/perf.html"],cwd=trees[tree],check=True,capture_output=True,env=dict(os.environ,PYTHONHASHSEED="0"))
        res.setdefault((name,tree),[]).append(time.perf_counter()-t)
for name,_,_ in targets:
    b,h=statistics.median(res[(name,"base")]),statistics.median(res[(name,"head")])
    print(f"| {name} | {b:.2f} | {h:.2f} | {h/b:.3f} |")
