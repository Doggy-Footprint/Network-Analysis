# LLM에 제공할 리포트 경량화

## User Query

> 보고서가 뭐 그렇게 무거워 왜 그래?

> 다른 handoff랑 그 무거운 것부터 어떻게 해결을 해야겠네..  -> 핸들오프 추가
> 핸드오프 정리해서 다른 핸드오프, 그리고 LLM 에게 제공할 보고서 경량화 과정을 거치게 하고 기존 데이터는 싹 폐기해 그냥.

배경: OSS 리팩토링 평가(`e16d433ef30afd87-oss-report-refactoring-eval.md`)에서 실험군 에이전트에게 리포트를 줄 준비를 하다가 크기 문제가 드러났다. 에이전트 14개가 병렬로 리포트를 읽으면 메모리가 부족하다. 평가 실험은 이 작업과 다른 handoff를 먼저 끝낸 뒤 진행한다.

## State

- 브랜치 `test/modal-sum-ranking`, HEAD `5ddd426`. 이 작업의 구현 변경은 없다.
- 측정에 쓴 리포트는 HEAD `5cbfbc1` 분석기로 만든 `eval/results/<repo>/before/`였고, 사용자 지시로 `./eval` 전체와 함께 삭제했다. 아래 수치는 재측정이 아니라 삭제 전 기록이다.

### 측정(삭제 전 파일 크기)

| repo | file 노드 / edge | `bottlenecks.json` | `report.json` |
|---|---|---|---|
| CTFd | 358 / 7,694 | 36MB | 32MB |
| flask-admin | — | 10MB | 18MB |
| lnbits | — | 29MB | 54MB |
| nowinandroid | — | 39MB | 38MB |
| ghostfolio | — | 115MB | 124MB |
| mealie | — | 53MB | 357MB |
| vendure | 3,706 / 308,340 | 684MB | 690MB |

- `bottlenecks.json`의 대부분은 `candidates[].evidence`다. vendure를 kind별로 보면 다음과 같다(compact `json.dumps` 길이 기준).
  - `evidence_spread` 2,056개: 516MB, 근거 항목 62.7만 개.
  - `dependency_cycle` 49개: 75MB.
  - `package_cycle` 50개: 76MB.
  - `unstable_dependency` 22,783개: 32MB.
  - `isolated_node` 60개: 0.4MB인데 근거 항목은 36.8만 개.
- CTFd에서는 `evidence_spread` 169개가 36MB 중 36.2MB를 차지했다.
- vendure에서 가장 큰 candidate는 `dependency_cycle` 하나로 71MB였다. 첫 근거는 `docs/scripts/compile-manifest.ts → scripts/docs/generate-graphql-docs.ts`(READS, tier `resolved`)였다.
- vendure `bottlenecks.json`을 Python `json.load`로 읽으면 RSS가 5.07GB였다.
- mealie `report.json`은 `details`(symbol 그래프: 노드 91,009개 78.5MB, edge 219,436개 125.5MB)가 228MB였다. file `edges`는 28.9MB(`CONFIGURES` 16.4MB)였다. indent=2 출력이라 compact보다 약 100MB 컸다.

### 원인(코드 위치)

- `bottlenecks/core.py:143` `evidence_record`: ambiguous edge는 `edge_to_dict`(`language_analyzers/core/serialization.py:46`) 전체를 근거로 복사한다. 이 dict에는 시각화 필드(`arrows`, `color`, `dashes`, `label`, `title`)도 들어 있다. 같은 edge가 여러 `evidence_spread` candidate에 반복 복사된다.
- `analysis/structure.py:164` `_cycle_candidates`: 순환 candidate가 SCC 내부 pair 전부(`internal`)를 근거로 담는다. pair마다 `detail_edge_indices`가 있다. tier(`all`, `resolved` 등)별로 같은 순환이 따로 나온다.
- `bottlenecks/reach.py:88` `isolated_node`: 관련 edge 전부를 `record(edge)`로 담는다.
- `code_analyzer/cli.py:474`: `report.json`을 `indent=2`로 쓴다.

## Failed Attempts

| attempt | failure evidence | cause |
|---|---|---|
| 평가 실험군에 리포트를 내용 그대로 key별·candidate별 JSONL로 분할해서 제공(설계만 하고 구현 안 함) | vendure 분할에도 `json.load` 5GB RSS가 필요하다. 사용자가 경량화를 먼저 하도록 결정했다 | verified: 사용자 결정. 분할은 제품의 크기 문제를 우회할 뿐 해결하지 않는다 |

## Next Step

1. 근거를 복사하지 않고 참조로 바꾼다. 근거 항목에는 `report.json`의 edge index만 둔다. 이미 `detail_edge_indices`라는 참조 방식이 있다. 시각화 필드는 JSON 출력에서 뺀다.
   - 프로젝트 원칙상 recall이 우선이다. 줄이는 것은 중복 표현이고, relation 자체는 빼지 않는다.
2. 순환 candidate는 `structure.cut_candidates`와 개수 지표를 기본으로 낸다. 내부 pair 전체 목록은 참조로 바꾸거나 별도 파일로 뺀다. tier별 중복 보고도 함께 정리한다(평가 handoff의 파일럿 결함 목록에도 있다).
3. `report.json`의 `details`(symbol 그래프)를 LLM용 출력에서 분리할지 정한다(Open Questions 참고). `indent` 제거도 함께 정한다.
4. 고친 뒤에는 실험 대상 7개 저장소의 리포트 크기와 `json.load` RSS를 다시 잰다. 그 결과로 Open Questions의 목표 크기를 확정한다.
5. `bottlenecks.v8` schema 버전 변경이 필요한지 확인한다. `bottlenecks/delta.py` 같은 리포트 비교 기능이 근거 형식에 의존하는지도 본다.

## Open Questions

- 기존 `report.json`/`bottlenecks.json` 자체를 줄일지, LLM용 출력(예: `--llm` 요약 파일)을 따로 만들지. HTML 리포트가 `details`와 시각화 필드를 쓰므로 둘의 소비자가 다르다.
- LLM용 출력의 목표 크기(예: 저장소당 수 MB, 또는 `json.load` RSS 상한).
- 순환에 docs/scripts 파일이 섞이는 문제(READS edge)를 이 작업에서 같이 다룰지, 별도 작업으로 둘지.

## Spec

없음. 이 작업을 시작할 때 `workflow-approach`로 spec을 만든다.

## Execution Ledger

없음. 측정은 삭제 전 리포트에 대해 Python `json.load`와 `json.dumps` 길이로 했다. 별도 도구는 쓰지 않았다.
