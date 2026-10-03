# Code Analyzer

저장소의 의존성 네트워크를 정적 분석하고, 구조적 병목을 리팩토링 검토 후보로 보여주는 도구입니다.

언어 수준의 import·호출·상속 관계에 의존성 주입, 라우팅, ORM과 마이그레이션처럼 프레임워크 의미로 드러나는 연결을 더합니다. 네트워크에서의 위치와 소스 코드의 토큰 규모를 함께 측정해 HTML 대시보드와 JSON 보고서로 출력합니다.

확실하지 않은 관계도 가능한 한 보존합니다. 각 연결의 신뢰도(`confidence`)와 해석 상태(`resolution`)를 기록하고, 설정한 가중치로 지표에 반영합니다. 결과는 사람이나 에이전트가 검토할 구조적 근거이며, 코드 품질·변경 위험·작업 난이도의 판정이나 AI 에이전트 행동의 예측은 아닙니다.

## 빠른 시작

이 저장소 루트에서 실행합니다. 분석 대상 애플리케이션을 실행할 필요는 없습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt

python -m code_analyzer /path/to/project -l python \
  -o local-reports/architecture.html --json \
  --bottlenecks local-reports/bottlenecks.json \
  --bottlenecks-html local-reports/bottlenecks.html
```

생성한 `local-reports/architecture.html`과 `local-reports/bottlenecks.html`을 브라우저에서 엽니다. `--open`을 추가하면 아키텍처 대시보드를 자동으로 엽니다.

| 출력 | 내용 |
| --- | --- |
| `architecture.html` | 의존성 그래프, 노드별 지표, 분석기별 구성 요소를 탐색하는 대시보드 |
| `architecture_assets/` | 대시보드의 CSS·JavaScript. HTML과 함께 보관해야 함 |
| `architecture.json` | `--json`으로 내보내는 그래프, 소스 위치, 연결 근거와 분석 메타데이터 |
| `bottlenecks.json` | `bottlenecks.v4` 형식의 지표별 순위, 분류별 순위, 병목 후보 |
| `bottlenecks.html` | 병목 JSON을 읽기 쉽게 보여주는 보고서 |

아키텍처 대시보드는 Tailwind CSS, vis-network, Lucide를 CDN에서 불러오므로 열람 시 네트워크 연결이 필요합니다.

## 지원 분석기

언어 분석은 `-l`, 프레임워크 분석은 `-f`로 선택합니다. 프레임워크 분석에는 기본적으로 해당 언어의 심볼 그래프도 포함됩니다.

| 구분 | 선택값 | 주요 분석 대상 |
| --- | --- | --- |
| 언어 | `-l python` | Python 모듈·클래스·함수, import·호출·타입 관계 |
| 언어 | `-l typescript` | TypeScript·JavaScript 심볼, import·export·호출·타입 관계, HTTP 호출 |
| 언어 | `-l kotlin` | Kotlin 선언, import·호출·상속·타입 관계 |
| 프레임워크 | `-f fastapi` | 앱·라우터·엔드포인트, `Depends`, Pydantic·SQLModel 스키마 |
| 프레임워크 | `-f android` | Compose, Hilt·Dagger, ViewModel, Room, Retrofit, Activity·Fragment |
| 프레임워크 | `-f sqlalchemy` | SQLAlchemy 모델·테이블, Alembic 마이그레이션과 모델의 연결 |
| 프레임워크 | `-f nestjs` | 앱 부트스트랩, 모듈·컨트롤러·프로바이더, 의존성 주입과 HTTP 라우트 |

### 사용 예시

```bash
# FastAPI
python -m code_analyzer /path/to/backend -f fastapi \
  -e app/main.py -o local-reports/fastapi.html

# Android
python -m code_analyzer /path/to/android-project -f android \
  -o local-reports/android.html

# NestJS
python -m code_analyzer /path/to/nestjs-project -f nestjs \
  -o local-reports/nestjs.html

# FastAPI + SQLAlchemy + TypeScript 클라이언트를 하나의 그래프로 분석
python -m code_analyzer /path/to/monorepo \
  -f fastapi -f sqlalchemy -l typescript \
  -o local-reports/combined.html --json \
  --bottlenecks local-reports/combined-bottlenecks.json \
  --bottlenecks-html local-reports/combined-bottlenecks.html
```

`-f`와 `-l`은 서로 섞거나 다른 선택값으로 반복할 수 있으며, 지정한 순서대로 같은 스냅샷을 분석합니다. 여러 분석기를 선택하면 그래프를 합친 뒤 전체 네트워크의 지표를 계산합니다.

- HTTP 연결: TypeScript·JavaScript의 `fetch`·Axios 호출과 Android의 Retrofit 엔드포인트를 FastAPI·NestJS 서버 라우트에 연결합니다(`CALLS_ROUTE`). 다중 분석기 실행에서 HTTP 메서드와 정규화한 경로로 매칭합니다.
- 마이그레이션 연결: SQLAlchemy 모델과 Alembic, Room 엔티티와 Room 마이그레이션을 테이블 이름으로 연결합니다(`MIGRATES`).
- 후보가 여러 개면 `ambiguous`로 표시하고 추가 대상을 `candidates`에 보존합니다. 매칭되지 않거나 정적으로 해석할 수 없는 경우는 매칭 통계에 남습니다.

같은 분석기 선택값의 중복 지정은 오류입니다. 서로 다른 분석기가 같은 노드 ID를 생성해도 오류가 납니다. 예를 들어 기본 설정의 `-f android -l kotlin`은 언어 그래프가 중복됩니다. SQLAlchemy와 FastAPI·Python, NestJS와 TypeScript 조합은 언어 노드의 중복 생성을 조정합니다.

## 보고서 읽기

### 네트워크 지표

병목 보고서는 지표별 상위 10개 노드와 `production`, `test`, `generated`, `vendored`, `unknown` 분류별 상위 10개를 제공합니다. 분류별 순위는 전체 그래프에서 계산한 지표를 분류별로 나눈 결과입니다.

| 지표 | 읽는 방법 |
| --- | --- |
| `pagerank` | 참조 관계가 모이는 노드의 상대적 중심성 |
| `hub_score`, `authority_score` | HITS로 계산한 참조하는 쪽과 참조받는 쪽의 중심성 |
| `degree_centrality`, `betweenness_centrality` | 직접 연결의 정도와 최단 경로의 중개 정도 |
| `fan_in`, `fan_out` | 들어오거나 나가는 연결 대상 수 |
| `weighted_fan_in`, `weighted_fan_out` | 연결 대상별 가중치의 합 |
| `weighted_centrality_cost` | `pagerank × effective_token_cost` |
| `hop_2_token_cost`, `hop_3_token_cost` | 연결 방향을 무시하고 2·3단계 이내로 도달하는 주변 노드의 `effective_token_cost` 합. 시작 노드는 제외 |
| `identifier_file_count` | 노드 이름의 마지막 식별자가 등장하는 스냅샷 내 파일 수. 코드·주석·docstring·문서·설정별 수도 제공 |

`identifier_file_count`는 노드별 지표에 포함되며 상위 10개 순위 항목에는 포함되지 않습니다. 단어 단위의 텍스트 출현 수이므로 동일 이름의 다른 심볼도 셉니다. 컨텍스트별 파일 수는 서로 겹칠 수 있습니다.

토큰 수는 모델별 토크나이저 대신 문자 수와 숫자 묶음으로 추정합니다. `effective_token_cost`는 이 추정치에 일반 코드 1, 생성 코드·마이그레이션 0.1, 외부 제공 코드 0의 배율을 적용한 값입니다. 여러 노드의 소스 범위가 겹칠 수 있으므로 합계를 저장소의 고유 텍스트 양이나 실제 LLM 사용량으로 해석하면 안 됩니다.

Betweenness는 기본적으로 500개 이하의 노드에서 정확하게 계산하고, 더 큰 그래프에서는 최대 100개의 결정적으로 선택한 시작 노드로 근사합니다. 보고서에 계산 전략과 표본 크기가 기록됩니다.

### 병목 후보

후보의 상태는 `static_candidate`입니다. 중심성 순위와 별도로 다음 근거를 제공합니다.

| 후보 종류 | 생성 조건 |
| --- | --- |
| `unresolved_boundary` | 미해결 참조, 동적 해석이 필요한 연결 또는 관련 노드 플래그가 있음 |
| `evidence_spread` | 같은 대상으로 들어오는 연결 근거가 여러 파일에 흩어져 있거나, 한 파일에서 근거의 줄 범위가 임계값을 초과함 |
| `large_node` | 노드의 소스 범위가 줄 수 임계값을 초과함. 기본값은 2,000줄 |

## 설정과 분석 범위

### 연결 가중치

기본 설정은 [profiles/edge_weights.v1.yaml](profiles/edge_weights.v1.yaml)입니다. 사용자 설정 파일은 다음처럼 선택합니다.

```bash
python -m code_analyzer /path/to/project -f fastapi \
  --edge-weights /path/to/edge_weights.yaml \
  -o local-reports/custom.html
```

연결 가중치는 신뢰도와 해석 상태의 가중치 중 작은 값입니다. 기본값은 `static_certain`과 `exact`·`unique_name`이 1.0, 나머지 등급이 0.3입니다. 같은 방향의 노드 쌍에 연결이 여러 개 있으면 가장 큰 가중치를 사용합니다.

이 설정은 PageRank, HITS, 가중 fan-in/out과 PageRank 기반 비용 지표에 반영됩니다. 연결 대상 수, degree·betweenness, hop 범위는 가중치로 축소하지 않습니다. `large_node_line_threshold`는 `large_node`와 한 파일 내 `evidence_spread`의 줄 수 임계값으로 사용됩니다.

### 저장소 스냅샷

CLI는 [profiles/snapshot.v1.yaml](profiles/snapshot.v1.yaml)에 따라 파일 내용을 한 번 읽어 모든 선택 분석기에 같은 불변 스냅샷을 전달합니다.

- Git 저장소에서는 기본적으로 추적 중인 파일의 **현재 작업 트리 내용**을 읽습니다. 커밋하지 않은 수정과 스테이징한 새 파일도 포함하지만, 아직 추적하지 않는 파일은 포함하지 않습니다.
- Git 파일 목록을 얻지 못하거나 목록이 비어 있으면 정적 디렉터리 순회로 대체합니다.
- 기본적으로 1 MiB를 초과하는 파일, 바이너리·읽을 수 없는 파일, 설정에 지정한 외부 코드·생성물·lockfile을 제외합니다. 파일 상단 8줄의 생성물 표기도 검사합니다.
- README·AGENTS·CLAUDE 문서는 기본적으로 포함합니다. 스냅샷에 들어간 파일 모두가 그래프 노드가 되는 것은 아닙니다.
- 이번 실행의 출력 파일과 대시보드 asset 디렉터리는 분석 대상에서 제외합니다.

스냅샷 설정을 바꾸려면 기본 YAML 파일을 수정합니다. 현재 CLI에는 별도 스냅샷 프로필 경로 옵션이 없습니다.

### 주요 CLI 옵션

| 옵션 | 동작 |
| --- | --- |
| `project_path` | 분석할 디렉터리. 생략하면 현재 디렉터리 |
| `-f`, `-l` | 분석기 선택. 둘 다 생략하면 FastAPI |
| `-o PATH` | 대시보드 HTML 경로. 기본값 `architecture.html` |
| `--json` | 대시보드 경로의 확장자를 `.json`으로 바꿔 그래프를 추가 출력 |
| `--bottlenecks PATH` | 병목 JSON 출력 |
| `--bottlenecks-html PATH` | 병목 HTML 출력. `--bottlenecks`가 함께 필요 |
| `-e PATH` | FastAPI 진입점 지정. FastAPI 분석기를 선택한 경우만 사용 가능 |
| `--no-language-graph` | 프레임워크 분석에서 기본 언어 그래프 제외 |
| `--no-models` | 해당 프레임워크의 스키마·모델·Room 엔티티 노드 제외 |
| `--no-deps` | 해당 프레임워크의 의존성 주입 구성 요소 제외 |
| `--edge-weights PATH` | 연결 가중치 설정 선택 |
| `--title TEXT`, `--open` | 대시보드 제목 지정, 브라우저에서 자동 열기 |
| `--mermaid` | 단일 프레임워크 분석의 Mermaid 다이어그램을 표준 출력으로 표시 |

CLI는 병목 보고서를 요청해도 아키텍처 대시보드를 함께 생성합니다. 각 출력 경로는 서로 달라야 합니다. 전체 도움말은 `python -m code_analyzer --help`로 확인합니다.

## 한계

- 정적으로 해석하는 패턴과 선택한 분석기가 분석 범위를 결정합니다. 동적 import, 실행 중 등록되는 의존성·라우트, 계산된 URL·테이블 이름 등은 연결을 확정하지 못할 수 있습니다.
- 라우트 매칭은 호스트를 제거한 메서드·경로 기준이고, 테이블 매칭은 스키마 접두사를 제거한 이름 기준입니다. 서로 다른 서비스나 데이터베이스의 동명 대상을 구분하지 못할 수 있습니다.
- 신뢰도 할인은 누락과 오탐을 없애지 않습니다. 높은 지표나 후보 표시는 소스 위치와 연결 근거를 함께 검토해야 합니다.
- 소스 위치나 명시적 비용이 없는 노드는 토큰 비용 추정에 대체 값을 사용할 수 있습니다. 관련 한계는 보고서에도 기록됩니다.

## 개발

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

활성 테스트는 `tests/`에서 수집합니다. 외부 저장소를 사용하는 테스트의 고정 커밋과 콘텐츠 해시는 [fixtures/registry.py](fixtures/registry.py)에 정의되어 있으며, 필요 시 `.fixtures/`에 내려받습니다.

이전 에이전트 탐색 네트워크, 검색 probe 재생, M1 보고서와 관련 프로필은 [archive/](archive/README.md)에 보관합니다. 현재 분석 파이프라인과 기본 테스트 수집에는 포함되지 않으며, 이전의 `--agent-view`, `--harness-profile` 옵션도 제공하지 않습니다.

- [프로젝트·에이전트 작업 지침](AGENTS.md)
- [아키텍처 결정 기록](adr/index.md)
- [진행 중인 작업 인계](agent-docs/handoff/index.md)
- [알려진 이슈](agent-docs/issues/index.md)
