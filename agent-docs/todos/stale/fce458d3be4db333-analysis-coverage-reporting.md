# 분석하지 못한 부분을 결과에 함께 보여주기

## Goal

사용자 요청: “Next 2개를 각각 handoff로 만들어줘.”

대상 Next: “분석하지 못한 부분을 결과에 함께 보여주기”. 출처: `tmp/is-my-code-ai-friendly.mdx`의 `## Next`. 이 복사본은 Git 추적 제외 대상이므로 재개에 필요한 내용은 아래에 기록한다.

## State

- 작성일: 2026-10-07. Branch: `master`. 기준 commit: `e0d6eff58e970e14dd265edd55c07d68e5e8c299`.
- 시작 시 추적 파일의 작업 트리는 깨끗했다. 이번 변경은 이 handoff, 함께 요청된 다른 Next handoff, `agent-docs/handoff/index.md`뿐이다.
- 상태: 개선 작업 미착수. 사용자는 handoff 작성을 요청했으며 세부 구현 정책은 아직 확정하지 않았다.
- `repository/scan.py`의 `build_snapshot`은 정책상 제외·읽기 실패 등의 사유를 `RepositorySnapshot.excluded_files`에 저장한다. Git 목록에 들어오지 않은 파일까지 모두 수집한 목록은 아니다.
- `PythonSourceAnalyzer._analyze_snapshot`은 대상 수, 파싱 성공 수, 실패 경로를 기록하고 Python 그래프는 `snapshot_coverage`로 보유한다.
- `bottlenecks/core.py:analyze_bottlenecks`의 공통 `coverage.source_file_count`는 `len(snapshot.contents)`다. 분석 성공 파일 수가 아니며, 제외 사유와 분석기별 성공·실패를 공통 요약으로 통합하지 않는다.
- 결과에 없는 파일을 “연결 없음”으로 오해할 수 있다. 언어·분석기별로 현재 제공하는 진단의 범위는 추가 조사가 필요하다.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 해당 없음 | 이 개선의 구현·수정 시도는 아직 없음 | 해당 없음; 실패 원인 진단 없음 |

## Next Step

1. 구현 재개 시 workflow-approach로 명세를 작성한다. 스캔→분석기→통합→파일 집계→JSON/HTML 경로에서 진단이 어디에 남고 어디서 사라지는지 확인한다.
2. “수집됨”, “선택한 분석기 대상”, “분석 성공/실패”, “정책상 제외”, “일부만 분석됨”의 의미와 집계 규칙을 사용자와 확정한다. 그래프에 노드가 생긴 것을 분석 성공의 정의로 대신하지 않는다.
3. 확정된 상태·건수·이유를 공통 결과와 화면에 전달한다. 관계 추출 규칙과 네트워크 지표를 바꾸는 작업은 별도 범위로 다룬다.
4. 정상 파일, 문법 오류, 크기 제한 제외, 대상 밖 언어, 여러 분석기가 공유하는 파일로 검증한다. JSON과 화면의 집계 일치 및 기존 관계·지표 불변을 확인한다.

## Open Questions

- 파일 단위 상태와 분석기 단위 상태를 어떻게 함께 표현할 것인가? 한 분석기 성공·다른 분석기 실패는 어떻게 집계할 것인가?
- 오류 복구 AST 등 부분 성공의 기준과 지원하지 않는 패턴의 표시 범위는 무엇인가?
- 공통 결과 스키마의 호환 정책과 화면에서 이유·경로를 노출할 범위는 무엇인가?
- Git 미추적 파일처럼 수집 목록 밖의 파일은 “집계하지 않은 범위”로 알릴지, 별도 수집할지? 후자는 아직 승인된 요구가 아니다.

## Spec

이 개선에 대한 활성·보관 명세 없음. Version, status, run ID: 해당 없음. 재개 시 별도 workflow 명세를 작성하며, 기존 기능의 명세를 이 개선의 승인 근거로 간주하지 않는다.

## Execution Ledger

- Finding: 위 State의 현재 동작을 기준 commit 코드에서 재확인했다. Disposition: 미해결 개선으로 이관; 구체적인 표현·집계 정책은 Open Questions에 남겼다.
- Evidence: `repository/scan.py`, `repository/models.py`, `language_analyzers/python/source.py`, `language_analyzers/python/graph.py`, `code_analyzer/cli.py`, `bottlenecks/core.py`, `report/unified.py`, `renderers/html/static/app.js`의 관련 경로를 읽어 확인했다. 이번 handoff 작성에서는 테스트나 성능 측정을 실행하지 않았다.
- Mutation outcomes: 구현 변경·뮤테이션 없음.
- Correction counter: 0. Verifier counter: 0. workflow 미시작 상태이며 검증 예산을 사용하지 않았다.

## Completion — 2026-10-07

- 완료: 파일·분석기별 관측 상태/이유, 공통 JSON 및 검색·필터·50행 HTML 상세 목록. 관계/지표와 읽기/파싱 횟수 보존 확인.
- Spec: `agent-docs/spec-logs/cfa172d091b48e63-analysis-coverage-reporting.md`, v2, complete, run `cfa172d091b48e63`. 상세 실패 시도와 원인은 spec Execution ledger에 보존.
- Evidence: `tests/coverage_reporting_evidence/coverage.json`; 현재 전체1132 tests/200 subtests 통과,6/6 confirming probes 검출·복원, 독립 audit2/2 pass, correction batches7, open findings none.
