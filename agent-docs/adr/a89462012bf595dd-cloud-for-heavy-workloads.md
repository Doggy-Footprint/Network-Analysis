# CPU·메모리 집약 작업은 GCP VM에서 수행한다

Status: Accepted

## Context
대형 저장소 분석기 실행과 병렬 에이전트 평가 run은 개발용 Mac의 메모리와 CPU를 넘는다. 측정값: bitwarden 분석이 swap 10.9/11GB 상태에서 OS에 의해 종료(rc -9), vendure `bottlenecks.json`(684MB) `json.load`에 RSS 5GB, 평가 설계는 16 run 병렬.

## Decision
- CPU·메모리 집약 작업(대형 저장소 분석기 실행, 프로파일링, 병렬 평가 run, 저장소 테스트 환경)은 GCP Compute Engine VM `na-eval`(project `playground-472408`, zone `asia-northeast3-a`, `n2-standard-16`: 16 vCPU, 64GB)에서 수행한다.
- 코드 수정, 단위 테스트, subagent 작업은 로컬에서 한다. 분석기 코드는 `git archive`로 VM에 올려 실행한다.
- VM은 작업할 때만 켜고, 작업이 끝나면 바로 중지한다. 삭제는 사용자가 명시할 때만 한다.

## Alternatives
- 로컬 Mac 실행: 위 메모리 한계로 대형 저장소 분석이 끝나지 않고 병렬 run이 불가능해 기각.

## Consequences
- 긍정: 메모리 한계로 인한 실패 없이 대형 저장소와 병렬 run을 처리한다.
- 부정: 실행 전후로 코드 업로드와 VM 시작·중지가 필요하고, 중지를 잊으면 비용이 든다. 외부 IP가 시작할 때마다 바뀐다.
