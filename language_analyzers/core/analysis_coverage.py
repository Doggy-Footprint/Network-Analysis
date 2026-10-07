from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from repository.models import RepositorySnapshot

_STATUSES = ('complete', 'partial', 'failed', 'skipped')


def _merge_status(statuses):
    values = set(statuses)
    if 'partial' in values or ('complete' in values and len(values) > 1):
        return 'partial'
    if 'failed' in values:
        return 'failed'
    return 'complete' if 'complete' in values else 'skipped'


def _reasons(reasons):
    unique = {json.dumps(reason, sort_keys=True, ensure_ascii=False): deepcopy(dict(reason)) for reason in reasons}
    return [unique[key] for key in sorted(unique)]


def analysis_report(analyzer_id: str, results: Sequence[Mapping[str, Any]]) -> dict:
    return {'analyzer_id': analyzer_id, 'results': deepcopy(list(results))}


def build_analysis_coverage(snapshot: RepositorySnapshot, reports: Sequence[Mapping[str, Any]]) -> dict:
    grouped = {}
    analyzer_ids = set()
    for report in reports:
        if 'analyzer_id' in report:
            producers = [report]
        else:
            producers = [analysis_report(producer['analyzer_id'], [
                {'file_path': row['file_path'], 'status': result['status'], 'reasons': result['reasons']}
                for row in report.get('files', ()) for result in row.get('results', ())
                if result['analyzer_id'] == producer['analyzer_id']
            ]) for producer in report.get('analyzers', ())]
        for producer in producers:
            analyzer_id = producer['analyzer_id']
            analyzer_ids.add(analyzer_id)
            for result in producer['results']:
                grouped.setdefault(result['file_path'], {}).setdefault(analyzer_id, []).append(result)
    summary = {key + '_file_count': 0 for key in ('inventory', 'collected', 'excluded', 'targeted', *_STATUSES, 'not_targeted')}
    producer_summaries = {key: {status + '_file_count': 0 for status in (*_STATUSES, 'targeted')} for key in sorted(analyzer_ids)}
    files = []
    excluded = {row.file_path: row.reason for row in snapshot.excluded_files}
    paths = set(snapshot.source_map) | set(excluded)
    for path in sorted(paths):
        results = []
        if path in excluded:
            status = 'excluded'
            reasons = [{'code': excluded[path], 'message': 'File excluded by repository scan: ' + excluded[path].replace('_', ' ')}]
        else:
            for analyzer_id, rows in sorted(grouped.get(path, {}).items()):
                producer_status = _merge_status(row['status'] for row in rows)
                results.append({'analyzer_id': analyzer_id, 'status': producer_status,
                                'reasons': _reasons(reason for row in rows for reason in row.get('reasons', ()))})
                producer_summaries[analyzer_id][producer_status + '_file_count'] += 1
                producer_summaries[analyzer_id]['targeted_file_count'] += 1
            status = _merge_status(row['status'] for row in results) if results else 'not_targeted'
            reasons = _reasons(reason for row in results for reason in row['reasons'])
            summary['collected_file_count'] += 1
            if results:
                summary['targeted_file_count'] += 1
        summary[status + '_file_count'] += 1
        files.append({'file_path': path, 'status': status, 'reasons': reasons, 'results': results})
    summary['inventory_file_count'] = len(paths)
    return {'version': 1, 'scope': {'ignore_source': snapshot.ignore_source, 'unlisted_files': 'not_enumerated'},
            'summary': summary, 'analyzers': [{'analyzer_id': key, 'summary': value} for key, value in producer_summaries.items()], 'files': files}


class CoverageRecorder:
    def __init__(self, snapshot, analyzer_id, discovered, extensions):
        self.snapshot = snapshot
        self.analyzer_id = analyzer_id
        self.results = []
        if snapshot is not None:
            selected = {Path(path).relative_to(snapshot.root).as_posix() for path in discovered}
            for path, _ in snapshot.contents:
                if Path(path).suffix in extensions and path not in selected:
                    self.record(path, 'skipped', [{'code': 'analyzer_excluded', 'message': 'File excluded by analyzer discovery rules'}])

    def record(self, path, status='complete', reasons=()):
        if self.snapshot is not None:
            self.results.append({'file_path': path, 'status': status, 'reasons': list(reasons)})

    def parsed(self, path, has_error):
        self.record(path, 'partial' if has_error else 'complete',
                    [{'code': 'syntax_error', 'message': 'Parser recovered from a syntax error'}] if has_error else [])

    def coverage(self):
        return build_analysis_coverage(self.snapshot, [analysis_report(self.analyzer_id, self.results)]) if self.snapshot is not None else {}


def attach_coverage(architecture, snapshot, *reports):
    if snapshot is not None:
        existing = architecture.stats.get('analysis_coverage')
        available = ([existing] if existing is not None else []) + [report for report in reports if report]
        if available:
            architecture.stats['analysis_coverage'] = build_analysis_coverage(snapshot, available)
