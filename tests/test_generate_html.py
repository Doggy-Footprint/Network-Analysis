import gzip
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import generate_html
from generate_html import ReportInputError, ReportOutputError, generate_report


ROOT = Path(__file__).resolve().parents[1]


def run_node(module_name, expression, payload):
    module_path = ROOT / "html_template" / module_name
    script = (
        "const fs=require('fs');"
        f"const model=require({json.dumps(str(module_path))});"
        "const data=JSON.parse(fs.readFileSync(0,'utf8'));"
        + expression
    )
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def run_generated_bootstrap(document):
    script = r"""
const fs=require('fs'); const vm=require('vm'); const html=fs.readFileSync(0,'utf8');
const calls={clear:0,arc:0,move:0,stroke:0,fillText:0}; const arcs=[]; const createdTags=[];
class Element {
  constructor(id,tag) { this.id=id; this.tagName=tag||'div'; this.children=[]; this.handlers={}; this.style={}; this.textContent=''; this.value=''; this.checked=false; this.hidden=false; this.width=0; this.height=0; }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child),1); return child; }
  get firstChild() { return this.children.length ? this.children[0] : null; }
  addEventListener(name,handler) { (this.handlers[name]||(this.handlers[name]=[])).push(handler); }
  getBoundingClientRect() { return {left:0,top:0,width:800,height:600}; }
  setPointerCapture() {}
  getContext() { return context; }
}
const context={beginPath(){},setLineDash(){},moveTo(x,y){calls.move+=1;},lineTo(){},stroke(){calls.stroke+=1;},closePath(){},fill(){},clearRect(){calls.clear+=1;arcs.length=0;},arc(x,y){calls.arc+=1;arcs.push([x,y]);},fillText(){calls.fillText+=1;},setTransform(){},globalAlpha:1};
const ids=['agent-view-data','report-title','profile-strip','summary-metrics','scan-summary','distribution-grid','graph-search','graph-find','graph-fit','filter-readable','filter-query','filter-framework','filter-query-kind','relationship-canvas','graph-empty','graph-status','graph-inspector','evidence-search','evidence-count','evidence-list','evidence-detail','excluded-files','unknown-edges'];
const elements={}; ids.forEach(id=>elements[id]=new Element(id,id==='relationship-canvas'?'canvas':'div'));
elements['filter-readable'].checked=true; elements['filter-query'].checked=true; elements['filter-framework'].checked=true; elements['filter-query-kind'].value='all';
const dataMatch=html.match(/<script id="agent-view-data" type="application\/json">([\s\S]*?)<\/script>/); elements['agent-view-data'].textContent=dataMatch[1];
global.window=globalThis; global.document={getElementById:id=>elements[id],createElement:tag=>{createdTags.push(tag);return new Element('',tag);}}; global.devicePixelRatio=1; global.addEventListener=function(){};
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(match=>match[1]); scripts.forEach(source=>vm.runInThisContext(source));
const textTree=node=>[node.textContent,...node.children.map(textTree)].filter(Boolean).join('|');
const initial={title:elements['report-title'].textContent,profile:elements['profile-strip'].children.map(textTree),metrics:elements['summary-metrics'].children.map(textTree),scan:elements['scan-summary'].children.map(textTree),distributions:elements['distribution-grid'].children.map(textTree),excluded:textTree(elements['excluded-files']),unknown:textTree(elements['unknown-edges']),domText:['report-title','profile-strip','summary-metrics','scan-summary','distribution-grid','evidence-list','excluded-files','unknown-edges'].map(id=>textTree(elements[id])).join('|')};
const evidenceDetails=[]; elements['evidence-list'].children.forEach(child=>{if(child.handlers.click){child.handlers.click[0]();evidenceDetails.push(elements['evidence-detail'].textContent);}});
const emit=(id,name,event)=>elements[id].handlers[name][0](event||{});
elements['graph-search'].value='helper'; emit('graph-find','click'); const searchInspector=elements['graph-inspector'].textContent; const beforeWheel=arcs.map(value=>value.slice());
emit('relationship-canvas','wheel',{preventDefault(){},deltaY:-1,clientX:120,clientY:100}); const afterWheel=arcs.map(value=>value.slice());
emit('relationship-canvas','pointerdown',{clientX:10,clientY:10,pointerId:1}); emit('relationship-canvas','pointermove',{clientX:30,clientY:35,pointerId:1}); emit('relationship-canvas','pointerup',{clientX:30,clientY:35,pointerId:1}); const afterPan=arcs.map(value=>value.slice());
emit('graph-fit','click'); const afterFit=arcs.map(value=>value.slice());
elements['filter-query'].checked=false; emit('filter-query','change'); const filteredStatus=elements['graph-status'].textContent; elements['filter-query'].checked=true; emit('filter-query','change');
elements['graph-search'].value='helper'; emit('graph-find','click'); elements['graph-inspector'].textContent='reset'; emit('relationship-canvas','pointerdown',{clientX:400,clientY:300,pointerId:2}); emit('relationship-canvas','pointerup',{clientX:400,clientY:300,pointerId:2}); const clickInspector=elements['graph-inspector'].textContent;
elements['evidence-search'].value='framework.rule'; emit('evidence-search','input');
process.stdout.write(JSON.stringify({initial,evidenceDetails,createdTags,title:elements['report-title'].textContent,evidence:elements['evidence-list'].children.length,evidenceCount:elements['evidence-count'].textContent,searchInspector,clickInspector,graphHandlers:Object.keys(elements['relationship-canvas'].handlers).sort(),filterHandler:(elements['filter-query'].handlers.change||[]).length,fitHandler:(elements['graph-fit'].handlers.click||[]).length,searchHandler:(elements['graph-find'].handlers.click||[]).length,evidenceHandler:(elements['evidence-search'].handlers.input||[]).length,emptyHidden:elements['graph-empty'].hidden,calls,beforeWheel,afterWheel,afterPan,afterFit,filteredStatus}));
"""
    result = subprocess.run(
        ["node", "-e", script],
        input=document,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def valid_payload():
    return {
        "schema_version": "2",
        "project_name": "샘플 <프로젝트>",
        "profile": {"id": "profile-v2", "version": 2, "content_hash": "abc123"},
        "readable_nodes": [
            {
                "id": "read:main",
                "file_path": "src/<main>.py",
                "symbol_id": "py:main",
                "label": "main <script>",
                "kind": "function",
                "start_line": 1,
                "end_line": 3,
                "read_cost": {"token_estimate": 12, "char_count": 48, "line_count": 3},
                "flags": ["entry"],
            },
            {
                "id": "read:helper",
                "file_path": "src/helper.py",
                "symbol_id": None,
                "label": "helper",
                "kind": "file",
                "start_line": None,
                "end_line": None,
                "read_cost": {"token_estimate": 7, "char_count": 28, "line_count": 2},
                "flags": [],
            },
        ],
        "query_nodes": [
            {
                "id": "query:main",
                "term": "</script><script>alert(1)</script>",
                "kind": "exact",
                "clue_kinds": ["identifier"],
                "origin_node_ids": ["read:main"],
                "rule_id": None,
                "source_terms": [],
                "occurrences": [
                    {
                        "file_path": "src/helper.py",
                        "line": 2,
                        "col": 4,
                        "matched_text": "helper",
                        "context": "code",
                        "enclosing_node_id": "read:helper",
                    }
                ],
                "occurrence_digest": "digest",
                "arrival_node_ids": ["read:helper"],
                "output_tokens": 5,
                "excluded": False,
                "exclusion_reason": None,
            }
        ],
        "framework_links": [
            {
                "id": "framework:one",
                "from_node_id": "read:main",
                "rule_id": "framework.rule",
                "specificity": "unique",
                "resolution": "exact",
                "to_node_ids": ["read:helper"],
                "candidate_node_ids": [],
                "query_id": None,
                "evidence_file": "src/main.py",
                "evidence_line": 2,
            }
        ],
        "unreachable_node_ids": ["read:main"],
        "scan": {
            "ignore_source": "git-tracked",
            "scanned_file_count": 2,
            "generated_file_count": 0,
            "generated_node_count": 0,
            "excluded_files": [{"file_path": "asset.bin", "reason": "binary"}],
            "unknown_framework_edges": ["unknown->edge"],
        },
    }


class GenerateHtmlTests(unittest.TestCase):
    def write_payload(self, directory, payload=None, name="graph.json"):
        path = Path(directory) / name
        path.write_text(json.dumps(payload if payload is not None else valid_payload()), encoding="utf-8")
        return path

    def test_generates_single_offline_report_with_required_sections(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            output = generate_report(source)
            document = output.read_text(encoding="utf-8")

        self.assertEqual(output.name, "graph.html")
        self.assertIn('data-component="summary"', document)
        self.assertIn('data-component="distributions"', document)
        self.assertIn('data-component="graph"', document)
        self.assertIn('data-component="evidence"', document)
        self.assertIn('data-component="glossary"', document)
        self.assertIn("프로젝트·profile·scan 요약", document)
        self.assertIn("전체 관계 그래프", document)
        self.assertIn("읽을 수 있는 대상", document)
        self.assertIn("근거 탐색", document)
        self.assertIn("readable node", document)
        self.assertIn("query node", document)
        self.assertIn("framework link", document)
        self.assertNotIn("https://", document)
        self.assertNotIn("http://", document)
        self.assertNotRegex(document, r'\b(?:src|href)\s*=')
        self.assertNotRegex(document, r"<(?:iframe|object|embed)\b")
        self.assertNotRegex(document, r"(?:@import|url\s*\()")
        network_pattern = re.compile(
            r"(?:fetch\s*\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|importScripts|import\s*\(|"
            r"setAttribute\s*\(\s*['\"](?:src|href)['\"]|\.(?:src|href)\s*=|"
            r"\[['\"](?:src|href)['\"]\]\s*=)",
            re.IGNORECASE,
        )
        self.assertNotRegex(document, network_pattern)
        sources = (ROOT / "generate_html.py").read_text(encoding="utf-8") + "\n" + "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted((ROOT / "html_template").iterdir())
            if path.suffix in {".html", ".js", ".css"}
        )
        inline_javascript = "\n".join(re.findall(r"<script>([\s\S]*?)</script>", document))
        self.assertTrue(inline_javascript)
        self.assertNotRegex(inline_javascript, network_pattern)
        self.assertNotRegex(sources, network_pattern)
        self.assertNotRegex(sources, r"(?:https?://|@import|url\s*\()")

    def test_generated_html_bootstraps_components_and_handlers(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            document = generate_report(source).read_text(encoding="utf-8")
        result = run_generated_bootstrap(document)

        self.assertEqual(result["title"], "샘플 <프로젝트> 탐색 구조")
        self.assertEqual(result["initial"]["profile"], [
            "schema|2",
            "profile|profile-v2 · v2",
            "content hash|abc123",
        ])
        self.assertEqual(result["initial"]["metrics"], [
            "readable nodes|2|읽을 수 있는 대상",
            "query nodes|1|검색 행동과 결과 묶음",
            "framework links|1|프레임워크 규칙 연결",
            "unreachable|1|현재 근거로 도달 불가",
            "read tokens|19|모든 읽기 비용 합계",
            "output tokens|5|모든 검색 출력 합계",
        ])
        self.assertEqual(result["initial"]["scan"], [
            "파일 목록 근거|git-tracked",
            "scan 파일|2",
            "generated 파일|0",
            "generated node|0",
            "제외 파일|1",
            "unknown framework edge|1",
        ])
        self.assertCountEqual(result["initial"]["distributions"], [
            "readable 종류|file|1|function|1",
            "read token|1–100|2",
            "query 종류|exact|1",
            "query 결과 수|1|1",
            "query output token|1–100|1",
        ])
        self.assertEqual(result["initial"]["excluded"], "asset.bin · binary")
        self.assertEqual(result["initial"]["unknown"], "unknown->edge")
        self.assertEqual(result["evidence"], 1)
        self.assertIn("1개 일치", result["evidenceCount"])
        self.assertIn("read:helper", result["searchInspector"])
        self.assertIn("read:helper", result["clickInspector"])
        self.assertEqual(result["graphHandlers"], ["pointerdown", "pointermove", "pointerup", "wheel"])
        self.assertEqual(result["filterHandler"], 1)
        self.assertEqual(result["fitHandler"], 1)
        self.assertEqual(result["searchHandler"], 1)
        self.assertEqual(result["evidenceHandler"], 1)
        self.assertGreater(result["calls"]["clear"], 0)
        self.assertGreater(result["calls"]["arc"], 0)
        self.assertGreater(result["calls"]["move"], 0)
        self.assertGreater(result["calls"]["stroke"], 0)
        self.assertGreater(result["calls"]["fillText"], 0)
        self.assertNotEqual(result["beforeWheel"], result["afterWheel"])
        self.assertAlmostEqual(result["afterPan"][0][0] - result["afterWheel"][0][0], 20)
        self.assertAlmostEqual(result["afterPan"][0][1] - result["afterWheel"][0][1], 25)
        self.assertNotEqual(result["afterPan"], result["afterFit"])
        self.assertEqual(result["filteredStatus"], "현재 viewport: node 2 · edge 1 · 전체 node 3 · 전체 edge 3 · viewport culling 적용")
        self.assertTrue(result["emptyHidden"])

    def test_summary_scan_counts_and_distributions_are_computed_from_input(self):
        result = run_node(
            "summary_model.js",
            "process.stdout.write(JSON.stringify({summary:model.createSummary(data),distributions:model.createDistributions(data)}));",
            valid_payload(),
        )

        self.assertEqual(result["summary"], {
            "projectName": "샘플 <프로젝트>",
            "schemaVersion": "2",
            "profile": {"id": "profile-v2", "version": 2, "contentHash": "abc123"},
            "metrics": {
                "readableNodes": 2,
                "queryNodes": 1,
                "frameworkLinks": 1,
                "unreachable": 1,
                "readTokens": 19,
                "outputTokens": 5,
            },
            "scan": {
                "ignoreSource": "git-tracked",
                "scannedFiles": 2,
                "generatedFiles": 0,
                "generatedNodes": 0,
                "excludedFiles": 1,
                "unknownFrameworkEdges": 1,
            },
        })
        self.assertEqual(dict(result["distributions"]), {
            "readable 종류": {"function": 1, "file": 1},
            "read token": {"1–100": 2},
            "query 종류": {"exact": 1},
            "query 결과 수": {"1": 1},
            "query output token": {"1–100": 1},
        })

    def test_embeds_every_node_and_relation_in_the_report_data(self):
        payload = valid_payload()
        for index in range(300):
            payload["readable_nodes"].append({
                "id": f"read:large:{index}",
                "file_path": f"src/large_{index}.py",
                "symbol_id": None,
                "label": f"large_{index}",
                "kind": "file",
                "start_line": None,
                "end_line": None,
                "read_cost": {"token_estimate": index, "char_count": index * 4, "line_count": 1},
                "flags": [],
            })
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory, payload)
            document = generate_report(source).read_text(encoding="utf-8")

        embedded = document.split('<script id="agent-view-data" type="application/json">', 1)[1].split("</script>", 1)[0]
        decoded = json.loads(embedded)
        self.assertEqual(len(decoded["readable_nodes"]), 302)
        self.assertEqual(len(decoded["query_nodes"]), 1)
        self.assertEqual(len(decoded["framework_links"]), 1)
        self.assertIn("viewport culling", document)

    def test_real_golden_graph_model_has_all_directed_edges_and_deterministic_coordinates(self):
        fixture = ROOT / "tests" / "fixtures" / "agent_view" / "realworld_app.json.gz"
        payload = json.loads(gzip.decompress(fixture.read_bytes()))
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "realworld.json"
            source.write_bytes(gzip.decompress(fixture.read_bytes()))
            document = generate_report(source).read_text(encoding="utf-8")
        embedded = document.split('<script id="agent-view-data" type="application/json">', 1)[1].split("</script>", 1)[0]
        generated_payload = json.loads(embedded)
        self.assertEqual(generated_payload, payload)
        result = run_node(
            "graph_model.js",
            """
const first=model.build(data); const second=model.build(data);
const expected=data.query_nodes.reduce((n,q)=>n+q.origin_node_ids.length+q.arrival_node_ids.length,0)
  +data.framework_links.reduce((n,l)=>n+l.to_node_ids.length+(l.query_id?1:0),0);
const edgeKeys=new Set(first.edges.map(e=>e.from+'|'+e.to+'|'+e.type));
const directions=data.query_nodes.every(q=>q.origin_node_ids.every(id=>edgeKeys.has('r:'+id+'|q:'+q.id+'|regular'))
  &&q.arrival_node_ids.every(id=>edgeKeys.has('q:'+q.id+'|r:'+id+'|regular')));
const frameworks=data.framework_links.every(l=>l.query_id
  ?edgeKeys.has('r:'+l.from_node_id+'|q:'+l.query_id+'|framework')&&l.to_node_ids.every(id=>edgeKeys.has('q:'+l.query_id+'|r:'+id+'|framework'))
  :l.to_node_ids.every(id=>edgeKeys.has('r:'+l.from_node_id+'|r:'+id+'|framework')));
const coordinates=graph=>JSON.stringify(graph.nodes.map(n=>[n.key,n.x,n.y]));
process.stdout.write(JSON.stringify({keys:first.nodes.map(n=>n.key).sort(),edges:first.edges.length,expected,directions,frameworks,deterministic:coordinates(first)===coordinates(second)}));
""",
            generated_payload,
        )

        expected_keys = sorted(
            [f"r:{node['id']}" for node in payload["readable_nodes"]]
            + [f"q:{node['id']}" for node in payload["query_nodes"]]
        )
        self.assertEqual(result["keys"], expected_keys)
        self.assertEqual(result["edges"], result["expected"])
        self.assertTrue(result["directions"])
        self.assertTrue(result["frameworks"])
        self.assertTrue(result["deterministic"])

    def test_graph_interactions_culling_and_evidence_search_execute(self):
        payload = valid_payload()
        derived = json.loads(json.dumps(payload["query_nodes"][0]))
        derived["id"] = "query:derived"
        derived["term"] = "derivedTerm"
        derived["kind"] = "derived"
        payload["query_nodes"].append(derived)
        graph_result = run_node(
            "graph_model.js",
            """
const built=model.build(data); const all={readable:true,query:true,framework:true,queryKind:'all'};
const fitted=model.fit(built,all,800,600); const panned=model.pan(fitted,17,-9);
const anchor={x:240,y:180}; const zoomed=model.zoomAt(fitted,1.12,anchor);
const before={x:(anchor.x-fitted.x)/fitted.scale,y:(anchor.y-fitted.y)/fitted.scale};
const after={x:(anchor.x-zoomed.x)/zoomed.scale,y:(anchor.y-zoomed.y)/zoomed.scale};
const found=model.find(built,'helper',all); const centered=model.center(found,fitted,800,600);
const point=model.screen(found,centered); const inspected=model.inspectAt(built,all,centered,point);
const smallCenter=model.center(found,fitted,80,60); const culled=model.selectVisible(built,all,smallCenter,80,60);
const readableOnly={readable:true,query:false,framework:false,queryKind:'all'};
const filtered=model.selectVisible(built,readableOnly,model.fit(built,readableOnly,800,600),800,600);
const otherKind={readable:true,query:true,framework:true,queryKind:'derived'};
const kindFiltered=built.nodes.filter(n=>model.visibleNode(n,otherKind));
const readableOff=built.nodes.filter(n=>model.visibleNode(n,{readable:false,query:true,framework:true,queryKind:'all'}));
const queryOff=built.nodes.filter(n=>model.visibleNode(n,{readable:true,query:false,framework:true,queryKind:'all'}));
const noFramework=model.selectVisible(built,{readable:true,query:true,framework:false,queryKind:'all'},fitted,800,600);
const boundaryNode=built.nodes[0]; const onBoundary=model.selectVisible(built,all,{scale:1,x:-boundaryNode.x-24,y:-boundaryNode.y+30},60,60); const pastBoundary=model.selectVisible(built,all,{scale:1,x:-boundaryNode.x-24.01,y:-boundaryNode.y+30},60,60);
const framework=built.edges.find(e=>e.type==='framework'); const a=model.screen(built.byKey[framework.from],fitted); const b=model.screen(built.byKey[framework.to],fitted);
const edgeInspection=model.inspectAt(built,all,fitted,{x:(a.x+b.x)/2,y:(a.y+b.y)/2});
process.stdout.write(JSON.stringify({fitted,panned,zoomed,before,after,found:found.value.id,point,inspected,edgeInspection,culledNodes:culled.nodes.length,totalNodes:built.nodes.length,filteredTypes:[...new Set(filtered.nodes.map(n=>n.type))],filteredEdges:filtered.edges.length,kindFilteredQueries:kindFiltered.filter(n=>n.type==='query').length,kindFilteredKinds:[...new Set(kindFiltered.filter(n=>n.type==='query').map(n=>n.value.kind))],readableOffTypes:[...new Set(readableOff.map(n=>n.type))],queryOffTypes:[...new Set(queryOff.map(n=>n.type))],frameworkEdges:noFramework.edges.filter(e=>e.type==='framework').length,regularEdges:noFramework.edges.filter(e=>e.type==='regular').length,onBoundary:onBoundary.nodes.some(n=>n.key===boundaryNode.key),pastBoundary:pastBoundary.nodes.some(n=>n.key===boundaryNode.key)}));
""",
            payload,
        )
        evidence_result = run_node(
            "evidence_model.js",
            "const items=model.build(data); const found=model.search(items,'framework.rule',200); const limited=model.search(items,'',2); const boundaries=model.boundaries(data); process.stdout.write(JSON.stringify({count:items.length,found:found.total,type:found.items[0].type,limited:limited.items.length,total:limited.total,excluded:boundaries.excludedFiles,unknown:boundaries.unknownFrameworkEdges}));",
            valid_payload(),
        )

        self.assertGreater(graph_result["fitted"]["scale"], 0)
        self.assertEqual(graph_result["panned"]["x"], graph_result["fitted"]["x"] + 17)
        self.assertEqual(graph_result["panned"]["y"], graph_result["fitted"]["y"] - 9)
        self.assertGreater(graph_result["zoomed"]["scale"], graph_result["fitted"]["scale"])
        self.assertAlmostEqual(graph_result["before"]["x"], graph_result["after"]["x"])
        self.assertAlmostEqual(graph_result["before"]["y"], graph_result["after"]["y"])
        self.assertEqual(graph_result["found"], "read:helper")
        self.assertEqual(graph_result["point"], {"x": 400, "y": 300})
        self.assertEqual(graph_result["inspected"]["data"]["id"], "read:helper")
        self.assertIn("edge", graph_result["edgeInspection"]["type"])
        self.assertGreater(graph_result["culledNodes"], 0)
        self.assertLess(graph_result["culledNodes"], graph_result["totalNodes"])
        self.assertEqual(graph_result["filteredTypes"], ["readable"])
        self.assertEqual(graph_result["filteredEdges"], 0)
        self.assertEqual(graph_result["kindFilteredQueries"], 1)
        self.assertEqual(graph_result["kindFilteredKinds"], ["derived"])
        self.assertEqual(graph_result["readableOffTypes"], ["query"])
        self.assertEqual(graph_result["queryOffTypes"], ["readable"])
        self.assertEqual(graph_result["frameworkEdges"], 0)
        self.assertGreater(graph_result["regularEdges"], 0)
        self.assertTrue(graph_result["onBoundary"])
        self.assertFalse(graph_result["pastBoundary"])
        self.assertEqual(evidence_result, {
            "count": 4,
            "found": 1,
            "type": "framework",
            "limited": 2,
            "total": 4,
            "excluded": [{"file_path": "asset.bin", "reason": "binary"}],
            "unknown": ["unknown->edge"],
        })

    def test_hostile_strings_are_inert_json_data(self):
        payload = valid_payload()
        hostile = lambda family: f"{family}</script><script data-hostile='{family}'>{family}</script>@@SCRIPTS@@"
        readable_main = hostile("readable-main-id")
        readable_helper = hostile("readable-helper-id")
        query_id = hostile("query-id")
        payload["project_name"] = hostile("project")
        payload["profile"] = {"id": hostile("profile-id"), "version": 2, "content_hash": hostile("profile-hash")}
        payload["readable_nodes"][0].update({
            "id": readable_main,
            "file_path": hostile("readable-file"),
            "symbol_id": hostile("symbol-id"),
            "label": hostile("readable-label"),
            "kind": hostile("readable-kind"),
            "flags": [hostile("readable-flag")],
        })
        payload["readable_nodes"][1].update({
            "id": readable_helper,
            "file_path": hostile("helper-file"),
            "symbol_id": hostile("helper-symbol"),
            "label": hostile("helper-label"),
            "kind": hostile("helper-kind"),
            "flags": [hostile("helper-flag")],
        })
        payload["query_nodes"][0].update({
            "id": query_id,
            "term": hostile("query-term"),
            "kind": hostile("query-kind"),
            "clue_kinds": [hostile("clue-kind")],
            "origin_node_ids": [readable_main],
            "rule_id": hostile("query-rule"),
            "source_terms": [hostile("source-term")],
            "occurrence_digest": hostile("occurrence-digest"),
            "arrival_node_ids": [readable_helper],
            "excluded": True,
            "exclusion_reason": hostile("query-exclusion"),
        })
        payload["query_nodes"][0]["occurrences"][0].update({
            "file_path": hostile("occurrence-file"),
            "matched_text": hostile("matched-text"),
            "context": hostile("occurrence-context"),
            "enclosing_node_id": readable_helper,
        })
        payload["framework_links"][0].update({
            "id": hostile("framework-id"),
            "from_node_id": readable_main,
            "rule_id": hostile("framework.rule"),
            "specificity": hostile("specificity"),
            "resolution": hostile("resolution"),
            "to_node_ids": [readable_helper],
            "candidate_node_ids": [readable_main],
            "query_id": query_id,
            "evidence_file": hostile("evidence-file"),
        })
        payload["unreachable_node_ids"] = [readable_main]
        payload["scan"]["ignore_source"] = hostile("ignore-source")
        payload["scan"]["excluded_files"][0] = {
            "file_path": hostile("excluded-file"),
            "reason": hostile("excluded-reason"),
        }
        payload["scan"]["unknown_framework_edges"] = [hostile("unknown-edge")]
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory, payload)
            document = generate_report(source).read_text(encoding="utf-8")

        embedded = document.split('<script id="agent-view-data" type="application/json">', 1)[1].split("</script>", 1)[0]
        decoded = json.loads(embedded)
        self.assertEqual(decoded, payload)
        rendered = run_generated_bootstrap(document)
        dom_text = rendered["initial"]["domText"] + "\n" + "\n".join(rendered["evidenceDetails"])

        def strings(value):
            if isinstance(value, str):
                return [value]
            if isinstance(value, list):
                return [item for entry in value for item in strings(entry)]
            if isinstance(value, dict):
                return [item for entry in value.values() for item in strings(entry)]
            return []

        for value in set(strings(payload)):
            self.assertIn(value, dom_text)
        self.assertNotIn("script", rendered["createdTags"])
        self.assertNotIn("</script><script data-hostile=", document)
        self.assertIn("&lt;/script&gt;&lt;script data-hostile=", document)

    def test_default_and_nested_explicit_output_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory, name="agent.view.json")
            default_output = generate_report(str(source))
            explicit_output = generate_report(str(source), str(Path(directory) / "nested" / "report.html"))

            self.assertEqual(default_output.name, "agent.view.html")
            self.assertEqual(default_output, source.with_suffix(".html").resolve())
            self.assertEqual(explicit_output.name, "report.html")
            self.assertTrue(default_output.is_absolute())
            self.assertTrue(explicit_output.is_absolute())
            self.assertTrue(default_output.is_file())
            self.assertTrue(explicit_output.is_file())
            self.assertIn("agent-view-data", explicit_output.read_text(encoding="utf-8"))

    def test_generation_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            first = generate_report(source, Path(directory) / "first.html").read_bytes()
            second = generate_report(source, Path(directory) / "second.html").read_bytes()

        self.assertEqual(first, second)

    def test_input_failures_raise_report_input_error(self):
        cases = (
            ("missing", None),
            ("invalid-json", "{"),
            ("invalid-utf8", b"\xff"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, content in cases:
                with self.subTest(name=name):
                    source = root / name
                    if isinstance(content, str):
                        source.write_text(content, encoding="utf-8")
                    elif isinstance(content, bytes):
                        source.write_bytes(content)
                    with self.assertRaises(ReportInputError):
                        generate_report(source)

    def test_unreadable_input_raises_report_input_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            with patch.object(Path, "read_text", side_effect=PermissionError("denied")):
                with self.assertRaises(ReportInputError):
                    generate_report(source)

    def test_schema_and_required_structure_failures_raise_report_input_error(self):
        mutations = (
            ("root", []),
            ("version", {**valid_payload(), "schema_version": "3"}),
            ("missing", {key: value for key, value in valid_payload().items() if key != "scan"}),
            ("collection", {**valid_payload(), "readable_nodes": {}}),
            ("nested", {**valid_payload(), "profile": {"id": "x", "version": "2", "content_hash": "x"}}),
        )
        with tempfile.TemporaryDirectory() as directory:
            for name, payload in mutations:
                with self.subTest(name=name):
                    source = self.write_payload(directory, payload, f"{name}.json")
                    with self.assertRaises(ReportInputError):
                        generate_report(source)

    def test_every_required_top_level_field_rejects_absence_and_wrong_type(self):
        wrong_values = {
            "schema_version": 2,
            "project_name": [],
            "profile": [],
            "readable_nodes": {},
            "query_nodes": {},
            "framework_links": {},
            "unreachable_node_ids": {},
            "scan": [],
        }
        with tempfile.TemporaryDirectory() as directory:
            for field, wrong in wrong_values.items():
                for mode in ("absent", "wrong-type"):
                    with self.subTest(field=field, mode=mode):
                        payload = valid_payload()
                        if mode == "absent":
                            del payload[field]
                        else:
                            payload[field] = wrong
                        source = self.write_payload(directory, payload, f"{field}-{mode}.json")
                        with self.assertRaises(ReportInputError):
                            generate_report(source)

    def test_malformed_nested_node_link_and_scan_fields_raise_report_input_error(self):
        cases = []
        payload = valid_payload()
        del payload["readable_nodes"][0]["id"]
        cases.append(("readable-missing-id", payload))
        payload = valid_payload()
        payload["readable_nodes"][0]["flags"] = "entry"
        cases.append(("readable-flags", payload))
        payload = valid_payload()
        payload["readable_nodes"][0]["read_cost"]["token_estimate"] = "12"
        cases.append(("readable-cost", payload))
        payload = valid_payload()
        payload["query_nodes"][0]["occurrences"] = {}
        cases.append(("query-occurrences", payload))
        payload = valid_payload()
        payload["query_nodes"][0]["occurrences"][0]["line"] = "2"
        cases.append(("occurrence-line", payload))
        payload = valid_payload()
        payload["query_nodes"][0]["excluded"] = "false"
        cases.append(("query-excluded", payload))
        payload = valid_payload()
        payload["framework_links"][0]["to_node_ids"] = "read:helper"
        cases.append(("framework-targets", payload))
        payload = valid_payload()
        payload["framework_links"][0]["evidence_line"] = "2"
        cases.append(("framework-evidence-line", payload))
        payload = valid_payload()
        payload["scan"]["excluded_files"] = {}
        cases.append(("scan-excluded", payload))
        payload = valid_payload()
        del payload["scan"]["excluded_files"][0]["reason"]
        cases.append(("scan-excluded-reason", payload))
        payload = valid_payload()
        payload["scan"]["unknown_framework_edges"] = {}
        cases.append(("scan-unknown", payload))

        with tempfile.TemporaryDirectory() as directory:
            for name, payload in cases:
                with self.subTest(name=name):
                    source = self.write_payload(directory, payload, f"{name}.json")
                    with self.assertRaises(ReportInputError):
                        generate_report(source)

    def test_duplicate_ids_raise_report_input_error(self):
        for collection in ("readable_nodes", "query_nodes", "framework_links"):
            with self.subTest(collection=collection), tempfile.TemporaryDirectory() as directory:
                payload = valid_payload()
                payload[collection].append(dict(payload[collection][0]))
                source = self.write_payload(directory, payload)
                with self.assertRaises(ReportInputError):
                    generate_report(source)

    def test_readable_and_query_ids_share_one_graph_namespace(self):
        with tempfile.TemporaryDirectory() as directory:
            payload = valid_payload()
            payload["query_nodes"][0]["id"] = "read:main"
            source = self.write_payload(directory, payload)
            with self.assertRaises(ReportInputError):
                generate_report(source)

    def test_every_dangling_reference_kind_raises_report_input_error(self):
        mutations = []
        for field in ("origin_node_ids", "arrival_node_ids"):
            payload = valid_payload()
            payload["query_nodes"][0][field] = ["missing"]
            mutations.append((f"query-{field}", payload))
        payload = valid_payload()
        payload["query_nodes"][0]["occurrences"][0]["enclosing_node_id"] = "missing"
        mutations.append(("occurrence", payload))
        for field in ("from_node_id", "to_node_ids", "candidate_node_ids"):
            payload = valid_payload()
            payload["framework_links"][0][field] = "missing" if field == "from_node_id" else ["missing"]
            mutations.append((f"framework-{field}", payload))
        payload = valid_payload()
        payload["framework_links"][0]["query_id"] = "missing"
        mutations.append(("framework-query", payload))
        payload = valid_payload()
        payload["unreachable_node_ids"] = ["missing"]
        mutations.append(("unreachable", payload))

        with tempfile.TemporaryDirectory() as directory:
            for name, payload in mutations:
                with self.subTest(name=name):
                    source = self.write_payload(directory, payload, f"{name}.json")
                    with self.assertRaises(ReportInputError):
                        generate_report(source)

    def test_empty_valid_graph_has_zero_and_empty_state(self):
        payload = valid_payload()
        payload["readable_nodes"] = []
        payload["query_nodes"] = []
        payload["framework_links"] = []
        payload["unreachable_node_ids"] = []
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory, payload)
            document = generate_report(source).read_text(encoding="utf-8")

        self.assertIn("표시할 관계가 없습니다", document)
        self.assertIn('data-empty-count="0"', document)
        result = run_generated_bootstrap(document)
        self.assertFalse(result["emptyHidden"])
        self.assertEqual(len(result["initial"]["metrics"]), 6)
        self.assertEqual(len(result["initial"]["distributions"]), 5)

    def test_same_input_and_output_raise_report_output_error_without_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            before = source.read_bytes()
            with self.assertRaises(ReportOutputError):
                generate_report(source, source)
            after = source.read_bytes()

        self.assertEqual(after, before)

    def test_resolved_dotdot_and_symlink_output_aliases_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            dotdot = Path(directory) / "unused" / ".." / source.name
            with self.assertRaises(ReportOutputError):
                generate_report(source, dotdot)
            alias = Path(directory) / "alias.json"
            try:
                alias.symlink_to(source)
            except OSError as error:
                self.skipTest(f"symlinks are unavailable: {error}")
            with self.assertRaises(ReportOutputError):
                generate_report(source, alias)

    def test_template_and_output_failures_raise_report_output_error(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            with patch.object(generate_html, "TEMPLATE_DIR", Path(directory) / "missing"):
                with self.assertRaises(ReportOutputError):
                    generate_report(source)
            output_parent_file = Path(directory) / "not-a-directory"
            output_parent_file.write_text("x", encoding="utf-8")
            with self.assertRaises(ReportOutputError):
                generate_report(source, output_parent_file / "report.html")
            with patch.object(Path, "write_text", side_effect=PermissionError("denied")):
                with self.assertRaises(ReportOutputError):
                    generate_report(source, Path(directory) / "denied.html")

    def test_cli_success_and_generation_error_exit_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            source = self.write_payload(directory)
            output = Path(directory) / "cli.html"
            success = subprocess.run(
                [sys.executable, str(ROOT / "generate_html.py"), str(source), "-o", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            failure = subprocess.run(
                [sys.executable, str(ROOT / "generate_html.py"), str(Path(directory) / "missing.json")],
                capture_output=True,
                text=True,
                check=False,
            )
            argument_error = subprocess.run(
                [sys.executable, str(ROOT / "generate_html.py")],
                capture_output=True,
                text=True,
                check=False,
            )
            output_error = subprocess.run(
                [sys.executable, str(ROOT / "generate_html.py"), str(source), "-o", str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            default_success = subprocess.run(
                [sys.executable, str(ROOT / "generate_html.py"), str(source)],
                capture_output=True,
                text=True,
                check=False,
            )
            default_exists = source.with_suffix(".html").is_file()

        self.assertEqual(success.returncode, 0)
        self.assertEqual(success.stdout.strip(), str(output.resolve()))
        self.assertEqual(failure.returncode, 1)
        self.assertIn("ReportInputError", failure.stderr)
        self.assertEqual(argument_error.returncode, 2)
        self.assertEqual(output_error.returncode, 1)
        self.assertIn("ReportOutputError", output_error.stderr)
        self.assertEqual(default_success.returncode, 0)
        self.assertEqual(default_success.stdout.strip(), str(source.with_suffix(".html").resolve()))
        self.assertTrue(default_exists)


if __name__ == "__main__":
    unittest.main()
