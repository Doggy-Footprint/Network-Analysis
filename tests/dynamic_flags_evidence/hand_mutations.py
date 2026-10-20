import json, subprocess, sys
from pathlib import Path
T="language_analyzers/typescript/analyzer.py"; TA="language_analyzers/typescript/ast.py"
KA="language_analyzers/kotlin/ast.py"; K="language_analyzers/kotlin/analyzer.py"; P="language_analyzers/python/graph.py"
M=[
 ("M1","R1 flag only for literal specifiers",T,"                module.dynamic_flags.add(flag_names.DYNAMIC_IMPORT)\n                arguments","                arguments", "test_V1"),
 ("M2","R3 checks first instead of second argument",T,"ts.call_argument(node, 1)","ts.call_argument(node, 0)","test_V3"),
 ("M3","R3 template with ${} treated as literal",TA,"        return child_of_type(node, \"template_substitution\") is None","        return True","test_V3"),
 ("M4","R2 new Function missed",T,"                    module.dynamic_flags.add(flag_names.DYNAMIC_EVAL)\n                continue","                    pass\n                continue","test_V2"),
 ("M5","R5 interpolated string treated as literal",KA,"        and not any(c.type.startswith(\"interpolat\") for c in expression.children)\n","","test_V5"),
 ("M6","D4 class attribution dropped",K,"        for flag in sorted(ka.dynamic_call_flags(symbol.node, source)):","        for flag in (sorted(ka.dynamic_call_flags(symbol.node, source)) if symbol.kind != NodeKind.CLASS else []):","test_V4"),
 ("M7","C14 rebound guard removed",P,"if alias is not None and alias[1] is not None and func.id not in self.rebound:","if alias is not None and alias[1] is not None:","test_V6"),
 ("M8","R6 if/try blocks ignored",P,"    for node in _walk_excluding_defs([\n        statement for statement in statements\n        if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))\n    ]):","    for node in statements:","test_V6"),
 ("M9","R8 only Load context",P,"        if not (isinstance(node.value, ast.Attribute) and node.value.attr == \"__dict__\"):","        if not (isinstance(node.value, ast.Attribute) and node.value.attr == \"__dict__\") or not isinstance(node.ctx, ast.Load):","test_V8"),
 ("M10","R9 module hook set includes __setattr__",P,"if _defines_hook(entry.tree.body, {\"__getattr__\"}):","if _defines_hook(entry.tree.body, _ATTRIBUTE_HOOKS | {\"__dir__\"}):","test_V9"),
]
res=[]
for mid,desc,path,old,new,sel in M:
    src=Path(path).read_text()
    assert src.count(old)==1,(mid,src.count(old))
    Path(path).write_text(src.replace(old,new))
    try:
        r=subprocess.run(["uv","run","-q","--with-requirements","requirements-dev.txt","python","-m","pytest","-q","-p","no:cacheprovider","tests/test_dynamic_flags.py","-k",sel],capture_output=True,text=True,timeout=600)
        tail=r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:]
        failed=[l.split(" ")[1] for l in r.stdout.splitlines() if l.startswith("FAILED")]
        killed = r.returncode==1 and bool(failed)
        res.append({"id":mid,"defect":desc,"file":path,"selector":sel,"killed":killed,"summary":tail,"failed_tests":failed[:6]})
        print(mid,killed,tail)
    finally:
        Path(path).write_text(src)
json.dump(res,open(sys.argv[1],"w"),indent=1,ensure_ascii=False)
