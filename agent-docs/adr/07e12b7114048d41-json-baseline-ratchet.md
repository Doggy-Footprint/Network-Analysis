# 구조 회귀 비교는 이전 bottleneck JSON을 baseline으로 쓴다

Status: Accepted

## Context
AI 변경 직후 구조 악화(새·커진 순환, 새 경계 위반)를 확인하려면 변경 전 상태와 비교해야 한다. 분석기는 repository snapshot(파일 내용) 단위로 동작하고 git history를 읽지 않는다.

## Decision
- `--baseline PATH`는 이전 실행이 만든 file granularity bottleneck JSON(`bottlenecks.v8`)을 받는다.
- 비교에 필요한 package 의존 쌍(`network.package_dependencies`)과 규칙 hash(`coverage.architecture_rules.rules_sha256`)는 모든 file granularity 실행 결과에 포함한다.
- schema, granularity, `structure_policy`가 다르거나 규칙 사용 여부가 다른 baseline은 오류(exit 1)다.

## Alternatives
- `--baseline-ref <git-ref>`(git worktree에 ref를 checkout해 두 번 분석): 실행 시간이 두 배가 되고, 분석 경로가 git에 의존하며, commit하지 않은 변경이나 git이 아닌 디렉터리를 baseline으로 쓸 수 없어 기각.
- 별도 baseline 저장 형식: 기존 bottleneck JSON과 형식이 이중화되어 기각.

## Consequences
- 긍정: baseline 생성은 일반 실행 한 번이고, CI artifact나 저장소에 둔 JSON을 그대로 쓴다.
- 부정: baseline이 쓰는 schema가 바뀌면 이전 baseline은 비교할 수 없어 다시 만들어야 한다. 출력에 비교 전용 필드가 상시 포함된다.
