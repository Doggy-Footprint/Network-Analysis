# 규칙표와 임계값을 버전 관리되는 profile 파일에 둔다

## Status

Accepted

## Context

ROADMAP은 derived query 규칙표와 비용 weight를 임시 값으로 정의하고, 실제 에이전트 로그로 보정한 뒤 교체할 것을 전제한다. 교체 전후의 비용은 같은 graph에서 비교해야 하고, 모든 결과는 어떤 규칙표로 산출됐는지 역추적할 수 있어야 한다.

## Decision

규칙표와 임계값을 `profiles/` 아래 버전이 붙은 YAML 파일에 두고, `Profile.ref`가 id, version, 파일 바이트의 sha256을 함께 보관한다. query node id는 `sha256(kind|term|profile.version)`의 앞 16자로 계산해 profile 버전이 바뀌면 id도 바뀐다. 직렬화된 graph는 항상 `profile` 필드를 포함한다.

`load_profile`은 규칙표에 등록되지 않은 변형 id를 `ProfileError`로 거부한다.

## Alternatives

- Python 모듈 상수: 값 교체가 코드 변경이 되어 분석 결과의 재현 조건과 코드 이력이 섞인다. 결과에 어떤 값이 쓰였는지 기록할 자리가 없다.
- JSON: 런타임 의존성이 늘지 않으나 규칙표에 주석을 달 수 없다.

## Consequences

- 긍정: 같은 저장소를 다른 profile로 분석한 두 결과를 profile id와 version으로 구분해 비교할 수 있다.
- 긍정: 규칙표 변경이 git 이력에 남고, 결과의 `content_hash`로 그 시점의 파일을 특정할 수 있다.

