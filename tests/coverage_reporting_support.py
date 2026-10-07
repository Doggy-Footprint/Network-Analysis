import copy
import importlib
import importlib.util
import json
from pathlib import Path

from repository import RepositorySnapshot

EVIDENCE = Path(__file__).parent / 'coverage_reporting_evidence'
IDS = ('python-core','typescript-core','kotlin-core','fastapi','android','sqlalchemy','nestjs')
ADAPTERS = {
 'python-core': ('language_analyzers.python.graph','PythonGraphAnalyzer','.py','class Example:\n    pass\n'),
 'typescript-core': ('language_analyzers.typescript','TypeScriptAnalyzer','.ts','export class Example {}\n'),
 'kotlin-core': ('language_analyzers.kotlin','KotlinAnalyzer','.kt','class Example {}\n'),
 'fastapi': ('framework_analyzers.fastapi.analyzer','FastAPIAnalyzer','.py','class Example:\n    pass\n'),
 'android': ('framework_analyzers.android.analyzer','AndroidAnalyzer','.kt','class Example {}\n'),
 'sqlalchemy': ('framework_analyzers.sqlalchemy','SQLAlchemyAnalyzer','.py','class Example:\n    pass\n'),
 'nestjs': ('framework_analyzers.nestjs','NestJSAnalyzer','.ts','export class Example {}\n'),
}
BUILDERS = {
 'fastapi': ('framework_analyzers.fastapi.graph','ArchitectureGraphBuilder','python-core'),
 'android': ('framework_analyzers.android.graph','AndroidArchitectureGraphBuilder','kotlin-core'),
 'sqlalchemy': ('framework_analyzers.sqlalchemy','SQLAlchemyGraphBuilder','python-core'),
 'nestjs': ('framework_analyzers.nestjs','NestJSGraphBuilder','typescript-core'),
}


def snapshot(root, files):
    return RepositorySnapshot(str(root.resolve()), 'snapshot.v1', tuple(sorted(files.items())), ())


def adapter(ident, root, snap):
    module, name, _, _ = ADAPTERS[ident]
    return getattr(importlib.import_module(module), name)(str(root), snapshot=snap)


def analyze(ident, root, snap, *, builder=False, language=True):
    obj = adapter(ident, root, snap)
    arch = obj.analyze()
    if builder and ident in BUILDERS:
        module, name, _ = BUILDERS[ident]
        arch = getattr(importlib.import_module(module), name)(snapshot=snap, include_language_graph=language).build_graph(arch)
    return arch


def coverage_of(arch):
    return arch.stats['analysis_coverage']


def own_result(coverage, path, ident):
    row = next(row for row in coverage['files'] if row['file_path'] == path)
    return next(result for result in row['results'] if result['analyzer_id'] == ident)


def baseline_runner():
    spec = importlib.util.spec_from_file_location('coverage_baseline_runner', str(Path(__file__).parent / 'coverage_characterization_runner.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def without_coverage(payload):
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    for record in result.values():
        record['architecture']['stats'].pop('analysis_coverage', None)
        record['bottlenecks']['coverage'].pop('analysis_coverage', None)
    return result


def dump(name, value):
    EVIDENCE.mkdir(exist_ok=True)
    (EVIDENCE/name).write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True))


def synthetic(count, producers=IDS, *, all_targeted=False):
    statuses = ('complete','partial','failed','skipped','not_targeted','excluded')
    files = []
    for i in range(count):
        status = statuses[i % (4 if all_targeted else 6)]
        reasons = [] if status == 'complete' else [{'code': 'oracle_code', 'message': f'oracle-reason-{i:05}'}]
        results = [] if status in ('excluded','not_targeted') else [{'analyzer_id': ident,'status':status,'reasons':copy.deepcopy(reasons)} for ident in producers]
        files.append({'file_path':f'src/oracle-{i:05}.py','status':status,'reasons':reasons,'results':results})
    counts = {status: sum(row['status']==status for row in files) for status in statuses}
    summary = {f'{status}_file_count': n for status,n in counts.items()}
    summary.update(inventory_file_count=count,collected_file_count=count-counts['excluded'],targeted_file_count=sum(counts[s] for s in statuses[:4]))
    return {'version':1,'scope':{'ignore_source':'provided','unlisted_files':'not_enumerated'},'summary':summary,'analyzers':[{'analyzer_id':ident,'summary':{**{f'{s}_file_count':counts[s] for s in statuses[:4]},'targeted_file_count':summary['targeted_file_count']}} for ident in sorted(producers)],'files':files}
