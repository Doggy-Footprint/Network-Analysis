import copy
from pathlib import Path
from types import SimpleNamespace

from language_analyzers.core.graph_models import GraphNode, NodeCost, SourceSpan
from repository import RepositorySnapshot

CHARACTERIZATION_FILES = {
    'one.kt': 'package one\nclass Duplicate\nclass Foo\nclass 한글\nfun `odd-name`() = 1\n',
    'two.kt': 'package two\nclass Duplicate\nfun create() = Duplicate()\n',
    'tests/Checks.kt': '''package checks
fun tests() {
  Foo(); Foo(); foo(); FooBar(); _Foo(); 한글()
  val text = "Foo 한글"
  // Foo 한글
  /* Foo */
  `odd-name`()
  fun nested() { Foo() }
  nested()
  Duplicate()
}
''',
    'prod.py': 'class Foo:\n    pass\ndef work():\n    return Foo()\n',
    'tests/test_prod.py': 'from prod import Foo, work\ndef test_work():\n    # Foo\n    return work(), work(), Foo(), "Foo"\n',
}


def snapshot(files, root='/file-oracle'):
    return RepositorySnapshot(root, 'snapshot.v1', tuple(sorted(files.items())), ())


def node(ident, path=None, kind='function', *, metadata=None, flags=()):
    return GraphNode(ident, ident, kind, kind, kind=kind, language='python',
                     span=SourceSpan(path, 1, 1) if path else None,
                     cost=NodeCost(999, 999, 999), metadata=copy.deepcopy(metadata or {}),
                     flags=list(flags), provenance='python-core')


def architecture(nodes=(), edges=(), root='/file-oracle'):
    return SimpleNamespace(project_name='oracle', project_path=root, nodes=list(nodes),
                           edges=list(edges), stats={}, report_collections=[])


def converted(files, nodes=(), edges=()):
    from analysis.file_graph import to_file_architecture
    snap = snapshot(files)
    return snap, to_file_architecture(architecture(nodes, edges), snap)


def serialize(arch):
    from language_analyzers.core.serialization import architecture_to_dict
    return architecture_to_dict(arch)


def characterization():
    from language_analyzers.kotlin import KotlinAnalyzer
    from language_analyzers.python.graph import PythonGraphAnalyzer
    from scripts.benchmark_file_analysis import raw_relations
    snap = snapshot(CHARACTERIZATION_FILES)
    root = Path(snap.root)
    return {name: raw_relations(serialize(builder(root, snapshot=snap).analyze()))
            for name, builder in [('kotlin', KotlinAnalyzer), ('tests', PythonGraphAnalyzer)]}
