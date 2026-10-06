# 파일 기본 분석과 심볼 상세 탐색: 완료

## Goal

> 기본 실행은 **파일 단위로 중심성과 병목 후보를 계산**하고, 같은 HTML에서 클래스·함수와 연결 근거를 탐색하게 한다. 기존 전역 심볼 분석은 선택 모드로 유지한다.

사용자의 승인된 명세 v1과 재개 요청 `file-analysis-paused handoff를 이어가줘`를 따른다. 새 run이나 기준선으로 검증 상한을 초기화하지 않는다.

## State

- 완료: 승인 v2의 file 기본 분석·같은 HTML의 symbol 상세 탐색, 명시 symbol·직접 API 원본값 보존.
- Branch:`fix/report-ui`; HEAD/base:`7eb255b0d552771c01e11fc2b4475663815c9567`. 커밋하지 않았다.
- 구현 변경: `README.md`, `code_analyzer/cli.py`, `analysis/{file_graph,graph_metrics}.py`, `repository/models.py`, `bottlenecks/core.py`, `language_analyzers/core/{annotate,cost,enrichment,positions,serialization}.py`, `language_analyzers/python/{graph,source}.py`, `language_analyzers/typescript/analyzer.py`, `language_analyzers/kotlin/analyzer.py`, `framework_analyzers/{fastapi,android,sqlalchemy,nestjs}/graph.py`, `framework_analyzers/{android,nestjs}/analyzer.py`, `renderers/html/static/{app.js,styles.css}`, `report/{unified.py,bottlenecks/generate.py}`.
- Tests 변경: `tests/conftest.py`, `tests/test_cli_{bottlenecks_v3,multi_analyzer,sqlalchemy}.py`, `tests/test_nestjs_{cli,quality}.py`, `tests/test_file_analysis_{core,cli,browser,benchmark}.py`, `tests/file_analysis_{support,browser_support}.py`, `scripts/benchmark_file_analysis.py`, `tests/unified_evidence/performance.json`, `tests/file_analysis_evidence/`.
- 최종 정상 실행:`pytest-run7.log`,1041passed/200subtests/680.26s, mandatoryskip0. Tag-Manager3회76.570/79.539/77.838s, median77.838≤180; original1238.087s. 원본 small/full관계·직접API4종3stage·기존symbolbyte·두browser5freshcontexts 검증통과.
- 독립 감사2/2:16의무/151선언항목 현행accepted, VF01/VF02/VF03closed; 열린필수지적·specchallenge·advisory없음. correction8/같은run상한유지.
- 세distinct defectclasses/fourprobes intended검출 후 모든sourceSHA복원. 동일Mermaidclass를file-arrow관측보강후재확인한것이며 fourthdistinctclass가아니다. 백업잔여없음.
- 정상suite7 source/Test SHA와13artifact/HTML SHA복원·focusedV08two cases2pass로현행증거를유지했다. mutant측정은mutation1–4폴더에분리보존했다. 원본baseline hash/실패/중단/미적용frontenddraft는유지했다.
- 최종 증거:`tests/file_analysis_evidence/{coverage.json,execution-revision.json,restoration-review.json,verifier2-audit.md,mutations.json,finding-dispositions.json}`. Source-review절차와API/원본CLI기대값의출처는architecture-review.md에있다.

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| X01: 구현 담당 실행 | `/root/implementation`이 “You’ve hit your usage limit”로 실패했다. 안내된 복구 시각은 2026-10-10 11:01 AM이며 시간대는 안내에 명시되지 않았다. 구현 파일은 변경하지 않았다. | verified: 지정된 gpt-6.1-sol 담당 실행의 사용량 한도 소진 |
| D01: 기준 실행 프로세스 확인 | `ps -axo ...`가 `operation not permitted: ps`로 실패했다. 기준 실행 자체는 이후 정상 완료했다. | verified: 현재 shell sandbox의 프로세스 조회 제한. 기준 실행 실패의 증거가 아니다. |
| R02: browser sandbox preflight | sandbox Chrome launch failed with SIGABRT/kill EPERM; identical require_escalated launch passed | verified: sandbox process restriction, resolved by approved elevated test execution |
| R04: review observer setup | scan-cache-review.py initially failed importing tests | verified: ROOT incorrectly pointed to parent directory; corrected before recording observations |
| R05: native sample attachment | first sample target process had exited | verified: stale worker PID; sampling a running file worker subsequently succeeded |
| R06: full suite1 | pytest-run1.log:13failed/1035passed/1error/192subtests; file median220.802s | verified: remaining name×symbol loops plus independent test oracle/selector/timer defects; corrected batch1 |
| R07: full suite2 | pytest-run2.log:3failed/1040passed/198subtests; file median73.879s, both browser datasets pass | verified: benchmark variable shadowing and two legacy symbol fallback-cost byte mismatches; artifact fixed batch2, compatibility requires policy decision |
| R09: provisional v1 suite3 interruption | pytest-run3.log, exit130; complete measurement series/whole-suite evidence 아님 | verified: user approved v2 while v1 test running; interrupted before v2 implementation and confirmed no running worker |
| R10: directAPI setup | focused4 tests initially TypeError before post-bottleneck assertions | verified: build_snapshot requires relative_paths; replaced setup with original explicit snapshot helper, immutable golden retained |
| R11: valid Unicode file | suite4passed but public U+2028 literal file span1..2 rejected by legacyLF validator | verified: file splitlines vs symbol LF bounds; file-only bounds corrected, suite5passed |
| R13: audit1 evidence gaps | verifier1-audit.md finds constantMermaid, boundary-free browser, internal/ownership candidate observation gaps | verified: existing assertions did not discriminate approved F09/A02/A05 violations; Tests-only correction6 |
| R14: focused correction6 | 1failed/36passed; fileMermaid expected4incl.env vsactual3 | verified: directAPI explicit snapshot universe differs from originalCLI scanner; originalCLI graph recaptured and expected source corrected, focused2pass |
| R15: fullsuite6 first launch | automatic approval review exceeded deadline; process not started | verified: review timeout; tool permitted one retry, which approved and fullsuite6passed |

## Next Step

요청 범위의 남은 작업 없음. 이 handoff와 이전 file-granularity 계획 handoff를 stale로 보관했다. source/Test/evidence변경 시 archivedspec의영향평가와실패기록을참조한다.

## Open Questions

없음. v2 사용자 선택은 file만1회계산, symbol기존계산·출력값보존이다. 원본fallback이이전metadata.analysis를포함해 모든CLI1회와기존symbol값이충돌한이유는 archivedspec A07/R08에남겼다.

## Spec

- Path:`agent-docs/spec-logs/0fc789ad2164e35b-file-analysis-symbol-details.md`
- Version2,statuscomplete,run_id`0fc789ad2164e35b`,max_verifier_invocations2.
- 원본frontendstaging은`agent-docs/spec-logs/0fc789ad2164e35b-frontend-staging.json`에보존한다.

## Execution Ledger

| attempt | findings and dispositions | evidence and mutation outcomes |
| --- | --- | --- |
| G00–G03/X01/P01 | 승인·기준선·사용량한도·사용자pause | 원본1238.087s/고정snapshot/실패·draft보존; 같은run재개 |
| R01–R08 | source/cache최적화·suite1/2·artifact교정·symbol계산호환정책충돌 | median220.802→73.879; 변수shadowing교정; 원본HEAD값으로fallback충돌확인,기준선변경없음 |
| R09–R12 | v2승인·suite3중단·directAPIsetup·Unicodefilevalidator보정 | file-onlysingle-pass/symbollegacy복원, 원본4API3stagegolden; validUnicode4tokens/13chars/2lines; suite5pass |
| R13–R16 | audit1세evidence공백; correction6/7 | Mermaidgraph/경계browser/내부vs소유dependency기대값보강; CLIvsAPI.env스냅샷차이원본CLI로교정; suite6pass |
| M01 | VF01 selectedMermaidcontentloss 검출 | constantgraph가file1vs3/symboldeclarationassertion실패; CLI원래SHA복원 |
| M02 | VF02boundarybrowserinclusion 검출 | exact3filelist에external-boundary추가되어실패; app.js원래SHA복원 |
| M03 | VF03internalactualdependencyloss 검출 | spread0vs1과unresolveduniqueinternal line4missing으로실패; core.py원래SHA복원 |
| R17–R20 | correction8같은Mermaid예제연결보강·사용자중단/재개 | 원본CLIlinked기대값2filearrows/6symbolarrows; globals/goldens불변; in-flight suite7재시작없이완료1041/200pass |
| M04/R21 | 같은Mermaidclass재확인·복원 | file0vs2/symbol0vs6arrowassertions실패; 모든source/Test SHA/13normalartifactSHA복원; focused2pass |
| R22 | freshaudit2pass/closure | 16currentaccepted/151items,3findingsclosed;8corrections/2verifiers/3classes4probes,backupsnone; speccomplete/archive/stalehandoffs |

전체 실패시도와 단계별 상세근거는 위 Failed Attempts 및 archivedspec Execution ledger에남아있다. 원본/실패/중단증거를최종정상실행으로덮어쓰지않았다.
