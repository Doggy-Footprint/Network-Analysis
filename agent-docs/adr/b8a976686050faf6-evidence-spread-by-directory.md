# evidence_spread를 디렉터리 단위로 판정

Status: Accepted

## Context
`evidence_spread`는 대상 노드로 들어오는 참조 근거가 흩어져 있는지를 후보로 낸다. 3회차(spec e91abc221d7deb2a) R5 이후 근거는 ownership 엣지와 대상 자기 파일을 뺀 나머지이고, 발동 조건은 "다른 파일 2개 이상"이었다.

file 모드에서 이 조건은 file 노드의 fan_in ≥ 2와 거의 같다. fixture의 file 모드 non-test 파일 중 이 조건으로 발동한 비율은 다음과 같았다.

| 입력 | 비율 |
| --- | --- |
| 이 저장소 | 75% |
| typescript-nestjs-realworld | 61% |
| android-nowinandroid | 56% |
| fastapi-realworld | 53% |
| futuramaapi | 46% |

후보 kind·id·metrics는 bottleneck JSON에 저장되고 baseline 비교의 키로 쓰인다.

## Decision
근거의 디렉터리(`posixpath.dirname(file_path)`, 루트는 `""`) 중 대상 파일의 디렉터리가 아닌 것의 수를 `directory_count`로 센다. 대상에 파일이 없으면 아무 디렉터리도 빼지 않는다.

발동 조건:
- `directory_count ≥ 2`, 또는
- `file_count == 1`이고 그 파일 근거의 줄 범위가 `large_node_line_threshold`보다 크다.

`file_count`·`line_span`·evidence 목록·후보 id·kind 이름은 그대로 유지한다. symbol 모드와 file 모드에 같은 정의를 쓰고, 보고서 정렬 지표는 `directory_count`다. schema 이름은 바꾸지 않고, `versions.analysis`는 "6"이다(spec 3f70cc03aeae9c1a).

## Alternatives
- 파일 수 임계를 설정값으로 노출(예: `evidence_spread_file_threshold`): 기각했다. 임계를 올려도 발동 조건이 file fan_in 임계와 같은 정보로 남는다.
- file 모드에서 `evidence_spread` 제거: 기각했다. 불확실한 신호도 버리지 않고 남긴다는 recall 우선 원칙에 어긋난다.

## Consequences
- (+) file 모드 non-test 발동 비율이 줄었다.

  | 입력 | 이전 | 이후 |
  | --- | --- | --- |
  | typescript-nestjs-realworld | 61% | 39% |
  | fastapi-realworld | 53% | 41% |
  | futuramaapi | 46% | 35% |
  | android-nowinandroid | 56% | 52% |

- (−) 디렉터리 구조에 따라 결과가 달라진다.
  - 파일 대부분이 다른 디렉터리 2곳 이상에서 쓰이는 저장소에서는 거의 줄지 않는다(이 저장소 75% → 72%).
  - 모든 파일이 한 디렉터리에 있는 저장소에서는 단일 파일 줄 범위 조건으로만 발동한다.
