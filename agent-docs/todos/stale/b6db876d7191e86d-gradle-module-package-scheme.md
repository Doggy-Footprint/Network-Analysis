# Gradle module을 framework package 체계에 추가

## Goal

> Architecture 분석 기능을 추가하고 싶어. goal: keep AI written codes maintanable

> pakcage의 정의가 있는 언어들은 자신의 정의를 쓰게하고, 그런 의미 단위를 정의하는 프레임워크도 마찬가지. 그게 없는 fallback으로 디렉터리 경로를 package로.

Android Gradle module(`:core:data` 등)을 `framework` package 체계에 포함할지 묻자, 사용자는 "이번에 제외, handoff 작성"으로 답했다. 이 문서는 그 제외된 작업을 인계한다.

## State

- Branch: `feat/archi`.
- Base commit: `6fda6d5a91eee508088292ad8b428694ee70b32f`.
- 변경된 파일: `agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md`, `agent-docs/adr/index.md`, 이 문서, `agent-docs/handoff/index.md`.
- 구현 변경은 없다. Gradle module 작업은 Phase 1(구조 사실) 이후에 시작한다. Phase 1이 `framework` 체계의 출력 형식을 먼저 확정해야 하기 때문이다.
- 관련 결정: `agent-docs/adr/58424b9754efe9a2-package-grouping-schemes.md`(체계별 계산, Gradle module 제외).

## Failed Attempts

| attempt | failure evidence | cause |
| --- | --- | --- |
| 구현 시도 없음 | 범위 결정 단계에서 사용자가 제외를 선택함 | verified: 사용자 답변 |

## Next Step

1. Phase 1 `framework` 체계의 package id 형식과 `unassigned` 집계 방식을 확인한다.
2. module 경계를 정한다.
   - `settings.gradle(.kts)`의 `include(...)`가 우선이다.
   - 없으면, 가장 가까운 상위 `build.gradle(.kts)` 디렉터리를 module 경계로 쓰는 방안을 검토한다.
   - 이 파일들은 이미 snapshot에 들어 있다. `language_analyzers/core/enrichment.py`에서 `.gradle`/`.gradle.kts`를 config 대상으로 다루기 때문이다.
3. module 간 선언 의존(`implementation(project(":core:model"))`)을 별도 edge로 추출할지 결정한다. 이 edge가 있으면 선언 의존과 코드 의존의 차이를 사실로 낼 수 있다.
4. 같은 방식으로 TS의 npm workspace `package.json`을 다룰지 함께 결정한다.

## Open Questions

- `settings.gradle`이 없는 단일 module repo에서 `framework` 체계를 생략할지, module 하나로 낼지.
- Gradle은 framework가 아니라 build system이다. 이를 `framework` 체계에 넣을지, `build` 체계를 따로 둘지. 따로 두면 ADR을 갱신해야 한다.
- `.fixtures/android-nowinandroid`는 일부 디렉터리만 고정한 shallow fixture다. `settings.gradle.kts`가 포함되어 있는지 확인해야 한다.

## Spec

none — workflow run 없음. 이 작업을 시작할 때 `workflow-approach`로 새 spec을 만든다.

## Execution Ledger

none — 실행한 workflow 없음.
