import json
import subprocess
import unittest
from pathlib import Path


APP = Path(__file__).resolve().parents[1] / 'renderers/html/static/app.js'


def run_js(body):
    script = f'''
const fs = require('fs');
const vm = require('vm');
globalThis.payload = {{nodes: [], edges: [], collections: {{}}, project_name: 'sample'}};
let callbacks = {{}};
let elements = new Map();
let exported = null;
const element = id => {{
  if (!elements.has(id)) {{
    let html = '';
    elements.set(id, {{id, writes: 0, innerText: '',
      get innerHTML() {{return html}}, set innerHTML(value) {{html = value; this.writes++}},
      classList: {{ add(){{}}, remove(){{}}, toggle(){{}} }},
    }});
  }}
  return elements.get(id);
}};
let ctx = {{
  ARCH_DATA: undefined,
  document: {{ getElementById: id => id === 'architecture-data'
    ? {{textContent: JSON.stringify(globalThis.payload)}} : element(id),
    addEventListener: (name, fn) => {{callbacks[name] = fn}},
    querySelectorAll: () => [], createElement: () => ({{click(){{}}}}) }},
  window: {{addEventListener(){{}}}}, lucide: {{createIcons(){{}}}},
  setTimeout: fn => fn(), console,
  Blob: class {{constructor(parts) {{exported = parts.join('')}}}},
  URL: {{createObjectURL: () => ''}},
  vis: {{DataSet: class {{
    constructor(items = []) {{this.items = []; this.add(items)}}
    add(items) {{this.items.push(...items)}}
    clear() {{this.items = []}}
    get(id) {{return id === undefined ? this.items : this.items.find(x => String(x.id) === String(id))}}
    update(items) {{for (const item of items) Object.assign(this.get(item.id), item)}}
  }}, Network: class {{
    constructor() {{this.focused = null}}
    on(){{}} once(){{}} setSize(){{}} redraw(){{}} fit(){{}}
    focus(id) {{this.focused = id}}
    getConnectedNodes() {{return []}}
    getConnectedEdges() {{return []}}
  }}}}
}};
vm.createContext(ctx);
ctx.ctx = ctx;
ctx.element = element;
ctx.exported = () => exported;
ctx.payload = globalThis.payload;
vm.runInContext(fs.readFileSync({json.dumps(str(APP))}, 'utf8'), ctx);
for (const name of ['ARCH_DATA', 'nodesDataSet', 'edgesDataSet', 'selectedNodeId', 'network']) {{
  Object.defineProperty(ctx, name, {{get: () => vm.runInContext(name, ctx)}});
}}
vm.runInContext({json.dumps(body)}, ctx);
'''
    result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class TestGraphSubset(unittest.TestCase):
    def test_b2_ties_use_string_id_order(self):
        result = run_js('''
const nodes = ['2','10', ...Array.from({length:199}, (_,i) => `z${String(i).padStart(3,'0')}`)]
 .map(id => ({id}));
console.log(JSON.stringify(ctx.selectGraphSubset(nodes, [], 200).nodes.map(n => n.id)));
''')
        self.assertEqual(result, ['10', '2', *[f'z{i:03d}' for i in range(198)]])

    def test_i1_incoming_edges_count_toward_degree(self):
        result = run_js('''
const nodes = [{id:'in'}, {id:'out'}, {id:'a'}, {id:'b'}, {id:'c'}];
const edges = [{from:'a',to:'in'}, {from:'b',to:'in'}, {from:'c',to:'out'}];
console.log(JSON.stringify(ctx.selectGraphSubset(nodes, edges, 1).nodes.map(n => n.id)));
''')
        self.assertEqual(result, ['in'])

    def test_n1_b1_b2_x1_ranking_cap_and_valid_edges(self):
        body = '''
const nodes = Array.from({length: 202}, (_, i) => ({id: String(i).padStart(3, '0')}));
const edges = Array.from({length: 201}, (_, i) => ({id: `e${i}`, from: '000', to: nodes[i + 1].id}));
edges.push({id: 'missing', from: '201', to: 'absent'});
const major = ctx.selectGraphSubset(nodes, edges, 200);
const small = ctx.selectGraphSubset(nodes.slice(0, 2), edges, 200);
const tied = ctx.selectGraphSubset(nodes, [], 200);
console.log(JSON.stringify({major: major.nodes.map(n => n.id), edges: major.edges.length,
 small: small.nodes.map(n => n.id), smallEdges: small.edges.length,
 tied: tied.nodes.map(n => n.id)}));
'''
        result = run_js(body)
        self.assertEqual(len(result['major']), 200)
        self.assertEqual(result['major'], [str(i).zfill(3) for i in range(200)])
        self.assertEqual(result['edges'], 199)
        self.assertEqual(result['small'], ['000', '001'])
        self.assertEqual(result['smallEdges'], 1)
        self.assertEqual(result['tied'], [str(i).zfill(3) for i in range(200)])

    def test_b3_focus_with_more_than_199_neighbors(self):
        result = run_js('''
const nodes = [{id:'z'}, ...Array.from({length: 202}, (_, i) => ({id:String(i).padStart(3,'0')}))];
const edges = nodes.slice(1).map(n => ({from:'z', to:n.id}));
edges.push({from:'000', to:'001'}, {from:'000', to:'002'});
const subset = ctx.selectGraphSubset(nodes, edges, 200, 'z');
console.log(JSON.stringify(subset.nodes.map(n => n.id)));
''')
        self.assertEqual(result, ['z', '000', '001', '002', *[str(i).zfill(3) for i in range(3, 199)]])

    def test_n3_search_omitted_node_without_prior_focus(self):
        result = run_js('''
const nodes = Array.from({length:202}, (_,i) => ({
 id:String(i).padStart(3,'0'), label:String(i).padStart(3,'0'), category:'thing'
}));
ctx.ARCH_DATA.nodes = nodes;
ctx.ARCH_DATA.edges = nodes.slice(1).map((n,i) => ({id:`e${i}`,from:'000',to:n.id}));
ctx.initNetwork();
const before = ctx.nodesDataSet.get().map(n => n.id);
ctx.handleSearch('201');
console.log(JSON.stringify({before, nodes:ctx.nodesDataSet.get().map(n => n.id),
 edges:ctx.edgesDataSet.get().map(e => e.id), focused:ctx.network.focused}));
''')
        self.assertNotIn('201', result['before'])
        self.assertEqual(result['nodes'], ['201', '000'])
        self.assertEqual(result['edges'], ['e200'])
        self.assertEqual(result['focused'], '201')

    def test_n2_n3_e1_x2_x3_x4_browser_flow(self):
        result = run_js('''
const nodes = Array.from({length: 202}, (_, i) => ({id:String(i).padStart(3,'0'), label:String(i).padStart(3,'0'), category:'thing'}));
const edges = nodes.slice(1).map((n, i) => ({id:`e${i}`, from:'000', to:n.id}));
globalThis.payload.nodes = nodes;
globalThis.payload.edges = edges;
globalThis.payload.collections = {
 things:{label:'Things', view:'table', columns:[{key:'id',label:'ID'}], rows:[{id:'201'}]},
 others:{label:'Others', view:'table', columns:[{key:'id',label:'ID'}], rows:[{id:'200'}]}
};
ctx.ARCH_DATA.nodes = nodes;
ctx.ARCH_DATA.edges = edges;
ctx.ARCH_DATA.collections = globalThis.payload.collections;
ctx.initNetwork();
const initial = ctx.nodesDataSet.get().map(n => n.id);
const initialEdges = ctx.edgesDataSet.get().map(e => e.id);
ctx.renderCollectionNavAndViews();
const before = element('collection-table-body-things').innerHTML;
const otherBefore = element('collection-table-body-others').innerHTML;
ctx.switchTab('things');
const first = element('collection-table-body-things').innerHTML;
const firstWrites = element('collection-table-body-things').writes;
ctx.switchTab('things');
const second = element('collection-table-body-things').innerHTML;
const secondWrites = element('collection-table-body-things').writes;
ctx.switchTab('others');
const otherFirst = element('collection-table-body-others').innerHTML;
const otherFirstWrites = element('collection-table-body-others').writes;
ctx.switchTab('others');
const otherSecondWrites = element('collection-table-body-others').writes;
ctx.focusNodeInGraph('201');
const focused = ctx.nodesDataSet.get().map(n => n.id);
const focusedEdges = ctx.edgesDataSet.get().map(e => e.id);
const inspected = ctx.selectedNodeId;
const inspectorTitle = element('inspector-title').innerText;
const unchanged = ctx.nodesDataSet.get().map(n => n.id);
const unchangedEdges = ctx.edgesDataSet.get().map(e => e.id);
const selectionBeforeUnknown = ctx.selectedNodeId;
ctx.focusNodeInGraph('absent');
const unknownUnchanged = JSON.stringify(unchanged) === JSON.stringify(ctx.nodesDataSet.get().map(n => n.id));
const unknownEdgesUnchanged = JSON.stringify(unchangedEdges) === JSON.stringify(ctx.edgesDataSet.get().map(e => e.id));
const selectionUnchanged = ctx.selectedNodeId === selectionBeforeUnknown;
ctx.handleSearch('201');
const searched = ctx.nodesDataSet.get().map(n => n.id);
const searchedEdges = ctx.edgesDataSet.get().map(e => e.id);
ctx.clearSearch();
const restored = ctx.nodesDataSet.get().map(n => n.id);
ctx.exportJSON();
const exportedData = JSON.parse(ctx.exported());
console.log(JSON.stringify({initial, initialEdges, before, otherBefore, first:first.length,
 second:first===second, firstWrites, secondWrites, otherFirst:otherFirst.length,
 otherFirstWrites, otherSecondWrites, focused, focusedEdges, inspected, inspectorTitle,
 unknownUnchanged, unknownEdgesUnchanged, selectionUnchanged, searched, searchedEdges,
 restored:restored.includes('201'), exportNodes:exportedData.nodes.map(n => n.id),
 exportEdges:exportedData.edges.map(e => e.id), exportRows:exportedData.collections.things.rows,
 exportOtherRows:exportedData.collections.others.rows}));
''')
        self.assertEqual(result['initial'], [str(i).zfill(3) for i in range(200)])
        self.assertEqual(result['initialEdges'], [f'e{i}' for i in range(199)])
        self.assertEqual(result['before'], '')
        self.assertEqual(result['otherBefore'], '')
        self.assertGreater(result['first'], 0)
        self.assertTrue(result['second'])
        self.assertEqual(result['firstWrites'], result['secondWrites'])
        self.assertGreater(result['otherFirst'], 0)
        self.assertEqual(result['otherFirstWrites'], result['otherSecondWrites'])
        self.assertEqual(result['focused'], ['201', '000'])
        self.assertEqual(result['focusedEdges'], ['e200'])
        self.assertEqual(result['inspected'], '201')
        self.assertEqual(result['inspectorTitle'], '201')
        self.assertTrue(result['unknownUnchanged'])
        self.assertTrue(result['unknownEdgesUnchanged'])
        self.assertTrue(result['selectionUnchanged'])
        self.assertEqual(result['searched'], ['201', '000'])
        self.assertEqual(result['searchedEdges'], ['e200'])
        self.assertFalse(result['restored'])
        self.assertEqual(result['exportNodes'], [str(i).zfill(3) for i in range(202)])
        self.assertEqual(result['exportEdges'], [f'e{i}' for i in range(201)])
        self.assertEqual(result['exportRows'], [{'id': '201'}])
        self.assertEqual(result['exportOtherRows'], [{'id': '200'}])

    def test_x3_reset_respects_active_filters(self):
        result = run_js('''
const nodes = Array.from({length:202}, (_, i) => ({
 id:String(i).padStart(3,'0'), label:String(i).padStart(3,'0'),
 category:i === 0 ? 'hide' : 'keep'
}));
ctx.ARCH_DATA.nodes = nodes;
ctx.ARCH_DATA.edges = nodes.slice(1).map((n,i) => ({id:`e${i}`,from:'000',to:n.id}));
ctx.initNetwork();
ctx.toggleFilterType('hide');
ctx.toggleFilterType('hide');
ctx.handleSearch('201');
const during = ctx.nodesDataSet.get().map(n => n.id);
const duringEdges = ctx.edgesDataSet.get().map(e => e.id);
ctx.clearSearch();
const after = ctx.nodesDataSet.get().map(n => n.id);
console.log(JSON.stringify({during,duringEdges,after,edges:ctx.edgesDataSet.get().map(e => e.id)}));
''')
        self.assertEqual(result['during'], ['201', '000'])
        self.assertEqual(result['duringEdges'], ['e200'])
        self.assertEqual(result['after'], [str(i).zfill(3) for i in range(1, 201)])
        self.assertEqual(result['edges'], [])
