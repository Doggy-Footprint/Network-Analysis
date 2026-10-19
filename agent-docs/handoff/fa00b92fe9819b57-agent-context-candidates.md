# 시그니처 맥락 비용(C)과 문서→코드 참조(D) 후보

## Goal

> 코드를 읽기 전에, AI agent의 작업 효율이 좋은 코드의 특징에 대한 최신 연구를 조사해줘.

> 자 그럼 이제, 우리가 정적 분석으로 지원할 수 있는 것들을 골라볼까?

> sonnet high subagent 호출해서 이미 지원하는 거 제대로 지원하고 있는지 검수해보고, C, D는 handoff에 넣어놓고, A, B는 이 세션에서 진행하자.

이 문서는 연구 조사에서 도출한 분석 후보 중 C와 D를 인계한다. A(테스트에 닿지 않는 허브)와 B(구조적으로 고립된 노드)는 같은 branch에서 별도로 진행한다.

## State

- Branch: `research/ai-friendly-code-structure`.
- Base commit: `6444895451a89f4450b9123b7beb17b11506e534`.
- 변경된 파일: 이 문서, `agent-docs/handoff/index.md`.
- C, D에 대한 구현 변경은 없다.

### 후보 정의와 근거

| id | 후보 | 근거 (scored-web-search 점수) | 관찰 가능한 정적 사실 |
| --- | --- | --- | --- |
| C | 시그니처만으로 줄일 수 있는 맥락 비용 | arXiv 2406.18294 Hierarchical Context Pruning (PRIMARY 80.3): 의존 파일의 함수 구현부를 제거해도 completion 정확도가 크게 떨어지지 않고, 파일 간 위상 의존을 유지하면 정확도가 오른다. | `GraphNode.signature`가 이미 있다. 2-hop 이웃을 시그니처만으로 셀 때의 토큰 비용을 기존 `hop_2_token_cost`와 나란히 낸다. |
| D | 문서→코드 참조 | HN 44957443(837점), 46809708(524점, Vercel eval: 8KB docs index를 AGENTS.md에 넣었을 때 pass rate 100%, skills 79%). 반대 근거: arXiv 2602.11988(SKIM 55.4), 저장소 개요는 도움이 안 되고 추론 비용을 20% 넘게 늘린다. | AGENTS.md와 docs의 경로·심볼 참조를 엣지로 만들고, 가리키는 대상이 없는(dangling) 참조를 낸다. |

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 구현 시도 없음 | 범위 결정 단계에서 사용자가 handoff를 선택함 | verified: 사용자 답변 |

## Next Step

1. C
   - `language_analyzers/core/cost.py`의 비용 정책과 `analysis/graph_metrics.py`의 `_node_token_cost`, `hop_2_token_cost` 계산을 확인한다.
   - 시그니처 비용을 언어별로 얻을 수 있는지 확인한다. Python은 `language_analyzers/python/symbols.py`, TypeScript와 Kotlin은 각 analyzer에서 `signature`를 채우는지 본다.
   - file granularity에서는 파일의 시그니처 비용을 소속 symbol 시그니처의 합으로 볼지 결정한다.
   - 새 지표는 ADR `31d2dee6912427d5-consolidate-overlapping-metrics.md`와 겹치는지 검토한다. 이 ADR은 순위 정보가 겹치는 지표를 제거한 기록이다.
2. D
   - 문서 파일은 현재 snapshot의 분석 대상이 아니다. `repository/scan.py`와 `repository/policy.py`에서 `.md` 포함 정책을 먼저 정한다.
   - 새 `RelationKind`(예: `DOCUMENTS`)와 그 confidence(`static_inferred`)를 정한다.
   - dangling 참조는 `unresolved_boundary`와 같은 방식(`resolution: unresolved`)으로 표현할 수 있는지 검토한다.

## Open Questions

- C: `hop_2_token_cost`와 순위가 거의 같다면 별도 지표로 둘 가치가 있는가. 위 ADR의 통합 기준을 그대로 적용할지 결정해야 한다.
- D: 문서 파일의 경로 표기(상대 경로, 백틱 코드 스팬, 마크다운 링크) 중 어디까지를 참조로 인정할 것인가.
- D: 저장소 개요 문서가 오히려 비용만 늘린다는 결과(SKIM 근거)가 있다. 이 상충을 후보 설명에 어떻게 드러낼 것인가.

## Spec

없음. C와 D에 대한 workflow는 시작하지 않았다.

## Execution Ledger

없음. 조사 단계의 출처 수치: 87개 수집 → 29개 통과 → 2개 판정 제외 → 20개 읽음 (논문 초록 8, HN 스레드 12).
