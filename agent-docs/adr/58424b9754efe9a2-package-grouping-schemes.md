# package 단위를 체계별로 따로 정의

Status: Accepted

## Context
file graph 위에 package 단위 지표(Ca, Ce, instability)와 package_cycle, unstable_dependency candidate를 추가한다. 이 값들은 bottleneck JSON에 package id로 저장되고, 이후 baseline 비교에서 키로 쓰인다.

repo마다 package의 의미가 다르다.
- Python은 module의 dotted 이름이 있다.
- Kotlin은 file의 `package` 선언이 있고, 디렉터리 경로와 다를 수 있다.
- TS/JS에는 언어 차원의 package가 없다.
- NestJS `@Module`은 언어 package와 무관하게 controller와 provider를 묶는다.

## Decision
package는 체계(scheme)별로 따로 계산한다. 각 체계 안에서만 Ca/Ce/instability를 비교하고 cycle을 계산한다.

- `language` 체계는 항상 계산한다.
  - Python: module의 상위 dotted package.
  - Kotlin: file의 `package` 선언(`kotlin-package:<name>` CONTAINS file 관계).
  - 언어 package 정의가 없는 언어(TS/JS 등): snapshot root 기준 file의 디렉터리 경로.
- `framework` 체계는 단위를 정의하는 framework가 분석에 포함된 경우에만 계산한다.
  - 대상: NestJS `@Module`.
  - 어느 단위에도 속하지 않는 file은 `unassigned`로 coverage에 집계한다.
- 이번 결정에서 제외한 것:
  - FastAPI `APIRouter`: 보통 file 하나에 router 하나여서 file과 단위가 같다.
  - Android Gradle module: build system 정의이고 현재 추출하지 않는다.

## Alternatives
- 우선순위 병합(framework 단위 > 언어 package > 디렉터리 순으로 file마다 하나를 고름): 기각했다. 한 graph 안에 NestJS module과 디렉터리처럼 크기가 다른 단위가 섞이면, package 사이의 instability 비교가 같은 척도를 잃는다.
- 디렉터리 경로만 사용: 기각했다. 언어나 framework가 package를 정의하면 그 정의를 쓴다는 사용자 결정에 어긋나고, Kotlin `package` 선언이 디렉터리와 다른 경우를 놓친다.

## Consequences
- (+) package id가 각 언어와 framework의 정의를 따르므로, 사용자가 코드에서 보는 이름과 같다.
- (−) 체계마다 지표와 candidate가 따로 나와 출력이 늘어난다. 저장된 package id가 baseline 비교 키이므로, 체계 정의를 바꾸면 이전 baseline과 package 단위 비교가 깨진다.
