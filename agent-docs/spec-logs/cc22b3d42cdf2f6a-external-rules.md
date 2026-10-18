---
version: 3
run_id: cc22b3d42cdf2f6a
status: complete
base_commit: 2627174d8a454a427965b5becee666c295454435
max_verifier_invocations: 2
handoff: none
---

# User Intent
| id | stakeholder | intention | observable goal |
| --- | --- | --- | --- |
| I1 | 사용자 | "Architecture 분석 기능을 추가하고 싶어. goal: keep AI written codes maintanable" | layer가 선언하지 않은 외부 library를 직접 import하면 `rule_violation` 구조 사실로 bottleneck JSON과 HTML에 나온다 |
| I2 | 사용자 | 외부 library 규칙은 Phase 2b run에서 (Phase 2 분리 결정) | 2a에서 예약한 `external`, `to_external` key가 동작한다 |
| I3 | 사용자 | 규칙 형식은 forbid + allow_external + group | 규칙 file에 `external` group, `forbid[].to_external`, `allow_external`을 쓸 수 있다 |
| I4 | 사용자 | TS는 tsconfig `paths` alias를 외부에서 제외 | 루트 `tsconfig.json`의 `compilerOptions.paths` alias specifier가 외부 import로 기록되지 않는다 |
| I5 | 사용자 | 규칙이 없어도 file별 외부 import를 항상 기록 | architecture JSON의 file node metadata에 `external_imports`가 있고, bottleneck JSON은 바뀌지 않는다 |

# Scope
In scope: Python·TypeScript·Kotlin analyzer의 외부 import 추출(analyzer node metadata `external_imports`), file 투영(file node metadata), TS 루트 tsconfig `paths`/`baseUrl` alias 제외, 규칙 YAML의 `external`·`forbid[].to_external`·`allow_external`, 외부 `rule_violation` candidate와 coverage 항목, 예제 profile 갱신, report validator·HTML 이유 표시.
Out of scope: stdlib 구분, Python `with`/`for`/`while`/`match` 블록 안의 import, Python 동적 import(importlib), Gradle·package.json·requirements 의존 정보, tsconfig `extends`·하위 디렉터리 tsconfig·project references, 외부 library를 graph node나 edge로 추가, 기존 지표·edge·candidate·Phase 1 구조 사실의 변경, symbol granularity 규칙 평가, 위반 시 exit code 변경과 baseline 비교(Phase 3), HTML Structure 패널(Phase 3), 외부 import 목록의 HTML 표시.

# Paths
Implementation: analysis/architecture_rules.py, analysis/structure.py, analysis/file_graph.py, language_analyzers/core/external_imports.py, language_analyzers/python/symbols.py, language_analyzers/python/graph.py, language_analyzers/typescript/analyzer.py, language_analyzers/kotlin/analyzer.py, bottlenecks/core.py, report/bottlenecks/generate.py, renderers/html/static/app.js, profiles/architecture_rules.example.yaml
Tests: tests/test_external_imports.py, tests/test_external_rules.py, tests/test_external_rules_integration.py, tests/test_external_rules_browser.py, tests/external_rules_support.py, tests/external_rules_evidence/, tests/test_architecture_rules.py, tests/test_architecture_rules_integration.py, tests/test_file_analysis_cli.py, tests/test_analysis_coverage_reporting.py, tests/test_nestjs_quality.py (기존 file은 다음 조정만 허용: 뒤의 세 file은 golden·characterization 비교 전에 node metadata의 `external_imports` key만 제거; 앞의 두 file은 F08·F15 때문에 깨지는 2a 테스트의 조정: "not supported" 기대, forbid key 집합, 예제 profile 내용·coverage key 집합, 외부 candidate에 없는 `to_layer` 접근. 변경은 `tests/external_rules_evidence/existing-tests.diff`에 기록)
Test command: uv run -q --with-requirements requirements-dev.txt python -c "from fixtures.registry import fixture_root; [fixture_root(n) for n in ('futuramaapi','fastapi-realworld','fastapi-official-template','android-nowinandroid','typescript-nestjs-realworld')]" && uv run -q --with-requirements requirements-dev.txt --with coverage python -m coverage run --branch --include=analysis/architecture_rules.py,language_analyzers/core/external_imports.py -m pytest -q -p no:cacheprovider && uv run -q --with coverage python -m coverage report --fail-under=90
Review evidence: R1 — main이 5개 fixture를 규칙 없이 `--json --granularity file --bottlenecks`로 실행하고 `tests/external_rules_evidence/size.json`(fixture별 `{base_architecture_bytes, architecture_bytes, ratio, external_import_count, files_with_external_imports}`)에 기록한다. fastapi-realworld는 예제 규칙과 함께도 실행해 `{no_rules_bottleneck_bytes, rules_bottleneck_bytes, ratio, violation_counts_by_rule}`를 기록한다. nestjs-realworld와 nowinandroid의 외부 import 상위 name 20개를 사람이 읽고 상식적인지(내부 alias나 repo package가 섞이지 않았는지) 확인한다. R2 — main이 예제 규칙을 적용한 fastapi-realworld HTML을 브라우저로 열어 외부 위반 이유 표시를 스크린샷으로 `tests/external_rules_evidence/`에 남긴다.
Fuzzing: main이 scratchpad에 작성한 stdlib 기반 harness, seed 20261018. (a) `load_architecture_rules`: 2a harness의 문서 변형에 `external`, `allow_external`, `to_external` key와 값을 추가. oracle crash — `ArchitectureRulesError` 외 예외 0, 20,000 입력. (b) `parse_tsconfig_aliases`: 무작위 JSONC 문자열(정상 tsconfig의 byte 변형, 주석·문자열·trailing comma 삽입). oracle crash — `ValueError` 외 예외 0, 20,000 입력. (c) `typescript_package_name`: 무작위 specifier. oracle property — 결과가 비어 있지 않고 입력의 접두이며, 결과에 다시 적용하면 같은 값이다(멱등), 20,000 입력.
Mutation tool: main이 scratchpad에 작성한 AST mutation 스크립트(2a와 같은 연산자). base_commit 이후 변경된 Implementation Python 줄만 대상. 최대 30개 표본, seed 20261018. 실행 명령 `uv run -q --with-requirements requirements-dev.txt python -m pytest -q -p no:cacheprovider -x tests/test_external_imports.py tests/test_external_rules.py tests/test_external_rules_integration.py`. 생존율 임계 40%.

# Signatures
`language_analyzers.core.external_imports.typescript_package_name(specifier: str) -> str` — F05 정규화.
`language_analyzers.core.external_imports.TsconfigAliases` (frozen dataclass): `path_keys: tuple[str, ...]`(`*` 단독 key 포함 모든 key, 입력 순서), `base_url: Optional[str]`(repo 루트 기준 정규화된 posix 디렉터리, 루트는 `""`)
`language_analyzers.core.external_imports.parse_tsconfig_aliases(text: str) -> TsconfigAliases` — F06. 잘못된 입력은 `ValueError`.
`language_analyzers.core.external_imports.is_typescript_alias(specifier: str, aliases: TsconfigAliases, source_files: Iterable[str]) -> bool` — F06. `source_files`는 repo 루트 기준 posix 경로.
`language_analyzers.core.external_imports.PythonModuleIndex(modules: Iterable[str], packages: Iterable[str])` — `.is_internal(name: str) -> bool`, F03.
`language_analyzers.core.external_imports.kotlin_is_internal(name: str, packages: Iterable[str]) -> bool` — F04.
`language_analyzers.core.external_imports.normalize_external_imports(records: Iterable[Mapping[str, Any]]) -> list[dict]` — F02 중복 제거·정렬.
`analysis.architecture_rules.ArchitectureRules`에 필드 추가(기본값 빈 mapping, 2a 생성자 호출과 호환): `external: Mapping[str, tuple[str, ...]]`(group → pattern, 정렬·중복 제거), `forbid_external: Mapping[str, tuple[str, ...]]`(from layer → entry, 정렬·중복 제거·같은 from 합집합), `allow_external: Mapping[str, tuple[str, ...]]`(layer → entry, 정렬·중복 제거). entry는 group 이름이거나 pattern이다.
`analysis.architecture_rules.external_entry_matches(rules: ArchitectureRules, entry: str, name: str) -> bool` — F09.
나머지 2a 시그니처(`load_architecture_rules`, `layer_assignments`, `match_path`, `analyze_structure(..., rules)`, `analyze_bottlenecks(..., rules)`)는 그대로다.

# Functional Requirements
| id | requirement | priority | source |
| --- | --- | --- | --- |
| F01 | 외부 import record는 mapping `{"name": str, "line": int}`(line은 `import`/`from`/`export`/`require`/`import(` 문이 시작하는 1-based 줄. Kotlin analyzer 기존 정규식이 앞 빈 줄 때문에 1 작은 줄을 내는 것은 기존 edge evidence에서만 유지하고 record에는 쓰지 않는다)이고, TS에서만 선택 key `"specifier": str`(원문 specifier가 name과 다를 때만), `"dynamic": true`(require/import() 호출일 때만)를 가진다. | required | I5 |
| F02 | record 목록은 같은 record(모든 key·값 동일)를 하나로 합치고 (name, line, specifier 또는 `""`, dynamic 여부 false<true) 순으로 정렬한다. 목록이 비면 metadata key를 만들지 않는다. | required | 결정성 |
| F03 | Python: module node metadata `external_imports`. 대상은 analyzer가 이미 수집하는 import 문 전부다: module 최상위, class body, function body(중첩 포함), 그리고 이들 안의 `if`/`try` 분기(body, orelse, finalbody, handlers, `TYPE_CHECKING` 포함)를 재귀로. `with`/`for`/`while`/`match` 블록 안의 import는 수집하지 않는다. `import a.b.c [as d]`는 alias마다 name `a.b.c`, `from a.b import c`(level 0)는 name `a.b`. 상대 import(level ≥ 1)와 `__future__`는 기록하지 않는다. 내부 판정 `PythonModuleIndex`: modules = analyzer가 발견한 모든 `.py` file의 module 이름(문법 오류로 파싱에 실패한 file 포함, `__init__` 제외), packages = 그중 `__init__.py` file의 module 이름. module M의 segment s₀…sₖ에서 위치 i가 root이려면 i = 0이거나 `s₀…sᵢ₋₁`이 packages에 없어야 한다. name N(segment n₀…nⱼ)이 내부이면 어떤 M과 root i에 대해 `sᵢ…sᵢ₊ⱼ` = N이다. 내부가 아닌 name만 기록한다. 예: modules {`backend.app`, `backend.app.core`, `backend.app.core.config`}, packages {`backend.app`, `backend.app.core`}에서 `app`·`app.core`·`backend.app`은 내부, `core`(root가 아닌 위치), `backend.x`(segment 불일치), `fastapi`는 외부. | required | I5, fastapi-official-template layout |
| F04 | Kotlin: file node metadata `external_imports`. analyzer가 이미 수집하는 `import` 문(정규식 `^\s*import\s+([\w.*]+)`)에서 name은 FQN, `.*`로 끝나면 `.*`를 뗀 package 이름이다. repo package 집합 = 선언된 `package` 이름(`<default>` 제외). `kotlin_is_internal(N)`은 어떤 repo package P에 대해 N = P, N이 `P.`로 시작, 또는 P가 `N.`로 시작하면 참이다. 내부가 아닌 name만 기록한다. | required | I5 |
| F05 | TS: module(file) node metadata `external_imports`. 대상은 정적 import·`import type`·export-from(`module_specifiers`)과 문자열 literal 인자의 `require`/`import()`(`dynamic_specifiers`, record에 `dynamic: true`)이다. specifier가 `.` 또는 `/`로 시작하거나 F06 alias이면 기록하지 않는다. name = `typescript_package_name(specifier)`: `@`로 시작하면 `/`로 나눈 앞 두 segment(segment가 하나면 전체), `node:`로 시작하면 첫 `/` 앞까지, 그 외에는 첫 `/` 앞까지. 예: `@nestjs/common/exceptions/http.exception`→`@nestjs/common`, `typeorm/common/DeepPartial`→`typeorm`, `node:fs/promises`→`node:fs`, `lodash`→`lodash`, `@scope`→`@scope`. | required | I5 |
| F06 | TS alias: repo 루트의 `tsconfig.json` 하나만 읽는다(snapshot 모드는 snapshot 내용, 아니면 file system). `parse_tsconfig_aliases`: 문자열 밖의 `//`·`/* */` 주석과 `}`/`]` 앞 trailing comma를 제거한 뒤 JSON으로 파싱한다. top-level이 object가 아니거나, `compilerOptions`가 object가 아니거나, `paths`가 문자열 key의 object가 아니거나, `baseUrl`이 문자열이 아니면 `ValueError`(key가 없으면 오류 아님). `is_typescript_alias(s)`: (a) `paths` key K가 `*`로 끝나고 K ≠ `*`이면 s가 K[:-1]로 시작할 때, K가 `*`로 끝나지 않으면 s = K일 때 참. key `*` 단독은 무시한다. (b) `baseUrl`이 있으면, tsconfig 디렉터리 기준으로 정규화한 baseUrl 디렉터리 아래 source file 각각의 첫 경로 segment(그 segment가 file 이름이면 확장자를 뗀 이름)가 s의 첫 `/` segment와 같을 때 참. 파일이 없으면 alias 없이 진행한다. 파싱 실패(`ValueError`)면 alias 없이 진행하고, analysis coverage(snapshot 모드에서만 존재)에 `tsconfig.json` 경로·analyzer `typescript-core`·status `partial`·reason code `tsconfig_invalid`를 기록한다. 정상 또는 부재일 때는 coverage에 아무것도 기록하지 않는다. | required | I4 |
| F07 | file granularity 투영: file node metadata `external_imports` = 그 file로 투영되는 analyzer node들의 `external_imports` 합집합(F02 적용, 비면 key 없음). file 모드 architecture JSON의 details node는 analyzer node 그대로 `external_imports`를 유지한다(기존 불변 조건: file 모드 details = symbol 모드 node, `tests/test_file_analysis_cli.py::test_V07`). boundary node 복사본에서는 key를 제거한다. symbol granularity에서는 analyzer node metadata에 그대로 남는다. 그 외 node·edge·지표·candidate는 바뀌지 않는다. | required | I5 |
| F08 | 규칙 문서 확장(version 1 유지): top-level 선택 key `external`, `allow_external` 추가. `external`은 비어 있지 않은 mapping이고 group 이름은 layer 이름과 같은 정규식, 값은 비어 있지 않은 문자열의 비어 있지 않은 list다. `forbid` 항목은 `from`(필수)과 `to`·`to_external` 중 하나 이상으로 이루어진 mapping이다(그 외 key 오류, 둘 다 없으면 오류). `to_external`과 `allow_external` 값의 원소(entry)는 비어 있지 않은 문자열이다. `group:`으로 시작하는 entry는 group 참조이고 나머지 부분이 `external`에 정의된 group 이름이어야 한다(아니면 오류). 그 외 entry는 pattern이다. `to_external`은 비어 있지 않은 list, `allow_external`은 mapping `layer → list`(빈 list 허용). 정의되지 않은 layer는 오류다. 목록은 정렬·중복 제거하고 같은 `from`의 `to_external`은 합집합한다. 사용되지 않은 group은 오류가 아니다. `to_external`만 있는 forbid 항목은 `forbid`(내부) mapping에 entry를 만들지 않는다. `allow_external: {}`는 유효하고 allow_external 규칙이 없는 것과 같다. 2a의 "not supported" 거부는 없어진다. | required | I2, I3 |
| F09 | entry 매칭 `external_entry_matches(entry, name)`: entry가 `group:<G>`이면 group G의 pattern 중 하나라도 `fnmatch.fnmatchcase(name, pattern)`이면 참, 아니면 `fnmatchcase(name, entry)`. 접두어가 없는 entry는 group 이름과 같더라도 pattern이다. | required | I3 |
| F10 | 외부 위반 판정: layer A에 배정된 file F(2a F05 배정, boundary 제외)의 `external_imports` 각 distinct name N에 대해 (a) `forbid_external[A]` entry 중 N에 매칭되는 것이 하나 이상이면 forbid_external 위반, (b) A가 `allow_external` key이고 `allow_external[A]` entry 중 N에 매칭되는 것이 없으면 allow_external 위반. 둘 다 해당하면 candidate 2개. 배정되지 않은 file은 위반이 없다. | required | I3 |
| F11 | 외부 `rule_violation` candidate: identifier `rule|<forbid_external\|allow_external>|<A>|<F>|<N>`, `kind` = `rule_violation`, `target` = F, `metrics` = {`evidence_count`: F에서 name N인 record 수}, `evidence` = 그 record 목록(F02 순서), `coverage` = `static_analyzer_relation`, `structure` = {`rule_type`, `from_layer`: A, `to_external`: N, `matched`: N에 매칭된 entry 목록(정렬, allow_external은 `[]`), `tier`: dynamic이 아닌 record가 있으면 `certain`, 아니면 `resolved`, `relations`: [`IMPORTS`]}. id·status는 `_candidate` 규칙, 전체 candidate (kind, id) 정렬은 2a와 같다. | required | 계획 |
| F12 | `coverage.architecture_rules`: 파싱된 `forbid_external` 또는 `allow_external` mapping에 key가 하나라도 있으면 `external_import_count`(boundary가 아닌 file node 전체의 record 수 합)와 `external_violation_count`(외부 candidate 수)를 추가한다. `violation_count`는 내부와 외부를 합친 수다. 외부 규칙이 없으면 coverage는 2a와 같다. | required | 계획 |
| F13 | 규칙이 없으면 bottleneck JSON은 base_commit 출력과 byte 단위로 같다. architecture JSON은 모든 node metadata(최상위 nodes와 details 포함)에서 `external_imports` key를 지우고 top-level `project_path`를 뺀 canonical 형태가 base_commit과 같다. 외부 규칙이 없는 2a 규칙 file의 결과도 2a와 같다. schema는 `bottlenecks.v8` 유지. | required | I5, 호환성 |
| F14 | `report/bottlenecks/generate.py`의 v8 검증이 외부 rule_violation과 F12 coverage key를 받아들인다. HTML file 모드에서 외부 위반은 target file 자리에 label `경계 규칙 위반`과 이유 `<from_layer> → <to_external> · <외부 금지 규칙\|외부 허용 목록 밖>`으로 text 삽입된다. 내부 위반 표시(2a + 도착 file 이름)는 바뀌지 않는다. | required | 계획 |
| F15 | `profiles/architecture_rules.example.yaml`에 다음을 추가하고 F08 검증을 통과한다: `external: {web: ["fastapi*", "starlette*"], db_driver: ["asyncpg*", "sqlalchemy*", "alembic*", "pypika*", "aiosql*"]}`, forbid `{from: db, to: [api], to_external: ["group:web"]}`(기존 db 항목 확장), `{from: api, to_external: ["group:db_driver"]}`, `allow_external: {domain: ["pydantic*", "typing", "datetime"]}`. 기존 2a 규칙은 유지. | required | R1 측정 |
| F16 | 같은 입력과 규칙의 결과는 실행마다 byte 단위로 같다(PYTHONHASHSEED 무관). | required | Phase 3 전제 |

# Errors
- 규칙 schema 위반(F08: `external` 형태, group 이름, 빈 pattern list, 정의되지 않은 `group:` 참조, forbid 항목 key 집합, `to_external` 빈 list·비문자열, `allow_external` 비 mapping·미정의 layer·비 list·비문자열) — `ArchitectureRulesError`(원인 key 또는 값 포함). CLI: stderr `[!] Error: ...`, exit 1, 출력 file 없음(2a와 같음).
- tsconfig 파싱 실패 — 오류가 아니다. alias 없이 계속하고 F06 coverage 기록, exit 0.
- tsconfig 부재, `paths`·`baseUrl` 부재 — 오류가 아니다. 기록 없음.
- 외부 import가 없는 file — metadata key 없음, 오류 아님.
- 위반 존재 — exit 0.

# Cases
| id | level | input / state | expected result |
| --- | --- | --- | --- |
| C01 | normal | Python repo `app/__init__.py`, `app/x.py`: `import os`, `import a.b as c`, `from fastapi import FastAPI`, `from app import x`, `from . import y`, `from __future__ import annotations` | `external_imports` name {`os`, `a.b`, `fastapi`}, 각 line 정확, `app`·상대·`__future__` 없음 |
| C02 | normal | Python `if TYPE_CHECKING: import sqlalchemy`, `try: import ujson except ImportError: import json`, 함수 안 `import requests`, class body 안 `import yaml`, 함수 안 `if` 분기의 `import attrs`, `with open(x): import toml`, `for _ in []: import tomli` | `sqlalchemy`, `ujson`, `json`, `requests`, `yaml`, `attrs` 기록, `toml`·`tomli` 없음 |
| C03 | boundary | `PythonModuleIndex` 표: modules {`backend.app`, `backend.app.core`, `backend.app.core.config`, `backend.app.main`, `scripts.tool`}, packages {`backend.app`, `backend.app.core`} × names {`app`✓내부, `app.core`✓, `app.core.config`✓, `app.missing`✗외부, `core`✗, `config`✗, `backend`✓, `backend.app`✓, `backend.x`✗, `scripts`✓, `tool`✓(`scripts`에 `__init__.py`가 없어 root), `fastapi`✗} | 표와 같음 |
| C04 | normal | Kotlin repo packages {`com.ex.app`, `com.ex.core.data`}, imports `androidx.room.Dao`, `com.ex.core.data.Repo`, `com.ex.app.ui.*`, `kotlinx.coroutines.*`, `com.ex.Shared`, `com.ex.*` | 외부 {`androidx.room.Dao`, `kotlinx.coroutines`, `com.ex.Shared`}; `com.ex`는 내부(P가 `com.ex.`로 시작) |
| C05 | normal | TS file: `import {A} from '@nestjs/common'`, `import type {B} from 'typeorm/common/DeepPartial'`, `export * from 'rxjs'`, `const f = require('node:fs/promises')`, `import('lodash')`, `import x from './y'`, `import z from '/abs'` | record name {`@nestjs/common`, `typeorm`(specifier 포함), `rxjs`, `node:fs`(specifier, dynamic), `lodash`(dynamic)}; 상대·절대 없음 |
| C06 | boundary | `typescript_package_name` 표: `@a/b/c`→`@a/b`, `@a`→`@a`, `@a/b`→`@a/b`, `node:fs`→`node:fs`, `node:fs/x`→`node:fs`, `a/b/c`→`a`, `a`→`a` | 표와 같음 |
| C07 | normal | tsconfig `{"compilerOptions": {"paths": {"@/*": ["src/*"], "@core": ["src/core/index.ts"], "*": ["types/*"]}}}` × specifiers `@/x`✓alias, `@/`✓, `@core`✓, `@core/x`✗, `@nestjs/common`✗, `lodash`✗ | 표와 같음, `*`는 무시 |
| C08 | normal | tsconfig `{"compilerOptions": {"baseUrl": "./src"}}`, files `src/app/x.ts`, `src/utils.ts`, `lib/z.ts` × specifiers `app/x`✓, `utils`✓, `lib/z`✗, `lodash`✗ | 표와 같음 |
| C09 | normal | JSONC tsconfig: `//` 주석, `/* */` 주석, 문자열 안의 `//`(`"http://x"`), trailing comma | 정상 파싱, 문자열 내용 보존 |
| C10 | error | tsconfig 잘못된 JSON, top-level list, `compilerOptions` 문자열, `paths` list, `baseUrl` 숫자 | `ValueError`; analyzer는 alias 없이 진행하고 coverage에 `tsconfig_invalid` partial 기록 |
| C11 | edge | tsconfig 없음 / `compilerOptions` 없음 | alias 없음, coverage 기록 없음 |
| C12 | normal | record 중복·순서 섞임 (같은 name 다른 line, 같은 line 중복, specifier 유무, dynamic 유무) | F02 순서·중복 제거 |
| C13 | normal | file 모드: 같은 file로 투영되는 analyzer node 2개(예: Python module node + framework node)의 record 합집합 | file node metadata에 합집합, details·boundary 복사본에는 key 없음 |
| C14 | error | 규칙 loader 오류 표: `external` 비 mapping/빈 mapping/group 이름 `1a`/값 빈 list/비문자열 pattern/빈 문자열; forbid 항목 `{from}`만, `{from, to_external: []}`, `{from, to_external: "x"}`, `{from, to_external: [1]}`, `{from, zz: [..]}`; `allow_external` list/미정의 layer/값 문자열/값에 빈 문자열; `to_external`·`allow_external`의 `group:missing`, `group:` | 각각 `ArchitectureRulesError`, 메시지에 원인 key 또는 값 |
| C15 | normal | 규칙 `external: {orm: [sqlalchemy*]}`, forbid `{from: d, to_external: ["group:orm", "fastapi"]}`와 `{from: d, to_external: ["group:orm"]}`, `allow_external: {d: ["pydantic*", "pydantic*"]}`, `{from: d, to: [x], to_external: [y]}` | 정상 load, 정렬·중복 제거·합집합, to와 to_external 동시 처리 |
| C16 | normal | 결정표: layer d file F의 names {`sqlalchemy.orm`, `fastapi`, `pydantic`, `os`}, group orm=[`sqlalchemy*`], forbid d→[`group:orm`, `fastapi`], allow_external d=[`pydantic*`] | forbid_external: `sqlalchemy.orm`(matched [`group:orm`]), `fastapi`(matched [`fastapi`]); allow_external: `sqlalchemy.orm`, `fastapi`, `os`; `pydantic` 위반 없음 |
| C17 | edge | group 이름이 package 이름과 같음(`external: {fastapi: ["starlette*"]}`), entry `fastapi`와 entry `group:fastapi` | `fastapi`는 pattern: `fastapi` 매칭, `starlette.x` 불일치. `group:fastapi`: `starlette.x` 매칭, `fastapi` 불일치 |
| C18 | edge | 배정되지 않은 file의 외부 import, allow_external key가 아닌 layer, 외부 import 없는 file | 위반 0 |
| C19 | normal | 같은 file에서 같은 name이 static 1회 + dynamic 1회 / dynamic만 | candidate 1개, evidence_count 2, tier certain / tier resolved |
| C20 | normal | coverage: 외부 규칙 있음 → `external_import_count`, `external_violation_count`, 합산 `violation_count`; 외부 규칙 없음 → 2a coverage와 같은 key 집합 | 명세대로 |
| C21 | normal | 5개 fixture를 규칙 없이 CLI(file 모드), 2개 fixture symbol 모드 | bottleneck JSON byte 같음, architecture canonical(F13) 같음, 각 fixture에서 `external_imports`가 있는 file node ≥ 1 |
| C22 | normal | fastapi-realworld 예제 규칙 CLI | forbid_external: `app/api/dependencies/database.py`→`asyncpg.connection`, `asyncpg.pool`; `app/db/events.py`→`fastapi`; allow_external(domain) 0; 2a 내부 위반 그대로; exit 0 |
| C23 | normal | fastapi-official-template 규칙 없이 | `backend/app/...` file의 `from app.core import ...`가 외부로 기록되지 않음, `fastapi`·`sqlmodel`은 기록 |
| C24 | normal | nestjs-realworld 규칙 없이 | `src/...` file record에 `@nestjs/common`, `typeorm` 존재, 상대 specifier 없음 |
| C25 | normal | nowinandroid 규칙 없이 (fixture는 sparse checkout이라 일부 module만 있음) | 분석된 snapshot에 선언된 package(그 하위·상위 포함, F04)로의 import는 미기록, snapshot에 없는 package로의 import와 `androidx.*`는 기록 |
| C26 | normal | 예제 규칙 HTML, 외부 위반 file 선택 | `경계 규칙 위반`, `db → fastapi · 외부 금지 규칙` 형식, 내부 위반 문구 그대로 |
| C27 | normal | 외부 위반 포함 v8 JSON을 `report.bottlenecks.generate`의 공개 함수(2a V09와 같은 경로)로 렌더링 | 성공 |
| C28 | normal | 같은 입력 두 번, PYTHONHASHSEED 다르게(외부 규칙 적용) | bottleneck·architecture JSON byte 같음 |
| C29 | boundary | 합성 20,000 file, file당 외부 name 20개, layer 10개, layer마다 forbid entry 10개 + allow_external entry 10개, group 5개(각 pattern 5개), 위반 (file, name) 쌍은 전체 400,000 쌍의 10% 이하(외부 candidate ≤ 40,000) | 외부 규칙 평가 시간(`analyze_structure`의 외부 규칙 있음 − 같은 규칙에서 외부 key만 뺀 것, 3회 중앙값) ≤ 5.0 s |
| C30 | edge | 2a 형식 규칙 file(외부 key 없음) | 2a와 같은 candidate·coverage |

# Quality Applicability
| ISO/IEC 25010:2023 characteristic | applicable | rationale |
| --- | --- | --- |
| Functional suitability | yes | 언어별 외부 판정과 규칙 판정이 명세대로여야 한다 |
| Performance efficiency | yes | 항상 기록이라 architecture JSON 크기가 늘어난다. 규칙 평가는 file × name × entry에 비례한다 |
| Compatibility | yes | 규칙이 없을 때 bottleneck JSON과 기존 graph가 바뀌면 안 된다 |
| Interaction capability | yes | 오류 메시지와 HTML 이유를 사람이 읽고 고칠 수 있어야 한다 |
| Reliability | yes | 결정성(Phase 3 전제), 깨진 tsconfig·규칙 file에서 crash 없음 |
| Security | yes | 사용자 YAML, 저장소의 tsconfig를 읽는다. 소스의 specifier 문자열이 HTML에 들어간다 |
| Maintainability | yes | 범용 analysis layer와 core helper가 언어별 analyzer를 import하면 안 된다 |
| Flexibility | yes | repo마다 바꿔 쓰는 규칙 설정 표면이다 |
| Safety | no | 물리적 위해와 관련 없는 정적 분석 도구다 |

# Quality Requirements
| id | characteristic / subcharacteristic | target and context | measure method / inputs / unit | threshold and direction | evidence: automated, review, mutation | source |
| --- | --- | --- | --- | --- | --- | --- |
| Q01 | Functional suitability / correctness | F01–F12 | 손 계산 기대값, 독립 oracle(support에 명세 문장으로 작성한 내부 판정·위반 판정) | 선언 coverage item 100% 통과 | automated + mutation | 계획 |
| Q02 | Performance efficiency / resource use | 규칙 없음 5개 fixture architecture JSON; fastapi-realworld 예제 규칙 bottleneck JSON | 새 byte ÷ base_manifest byte; 규칙 적용 ÷ 규칙 없음 | architecture ≤ 1.05(각 fixture), bottleneck ≤ 1.25 | automated + review R1 | 측정: 외부 import 문 183–855개, record 약 60 byte |
| Q03 | Performance efficiency / time behaviour | C29 | 같은 process 3회 중앙값, 초 | ≤ 5.0 s | automated | 2a와 같은 수준 |
| Q04 | Compatibility / coexistence | 규칙 없음, 2a 규칙 | C21, C30, base_manifest 비교 | 차이 0, 기존 pytest 실패 0 | automated | F13 |
| Q05 | Interaction capability / user error protection | 규칙 loader 오류 | C14 | 메시지에 원인 key(`external`, `to_external`, `allow_external`, group 이름) 또는 값 포함 | automated | 2a Q05 |
| Q06 | Interaction capability / recognizability | HTML 외부 위반 | C26 | label과 이유 문자열 일치 | automated(Playwright) + review R2 | F14 |
| Q07 | Reliability / faultlessness | 결정성, 잘못된 입력 | C28, fuzz (a)(b)(c) | byte 차이 0, 허용 예외 외 0, property 위반 0 | automated + fuzz | F16 |
| Q08 | Security / integrity | YAML, tsconfig, HTML | `!!python/object` 태그 규칙 문서, tsconfig 파서가 코드 실행 없이 JSON만 해석, 적대적 specifier(`<img src=x onerror=...>`) 이유 표시 | 태그 문서 ArchitectureRulesError, script 실행 0 | automated | `tests/test_report_security.py` 정책 |
| Q09 | Maintainability / modularity | `analysis/architecture_rules.py`, `language_analyzers/core/external_imports.py` | AST import 검사 | 앞의 것은 `language_analyzers`·`framework_analyzers` import 0, 뒤의 것은 `language_analyzers.<python\|typescript\|kotlin>`·`framework_analyzers`·`analysis` import 0 | automated | 프로젝트 경계 |
| Q10 | Maintainability / testability | 두 module | coverage.py branch(Test command) | ≥ 90% | automated | 2a와 같음 |
| Q11 | Flexibility / adaptability | 예제 profile | F15 문서 load, C22 결과 | load 성공, C22 통과 | automated | F15 |

# Verification Obligations
| id | parent requirement/Case ids | variant and target surface | test layer and selection policy | ISO/IEC/IEEE 29119-4 technique | coverage items | coverage target | observation and expected result | evidence procedure |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V01 | F03, C01, C02 | Python analyzer module node metadata | unit; tmp_path repo + `PythonAnalyzer`(또는 CLI 공개 경로) | equivalence partitioning | import-plain; import-dotted-alias; from-absolute; from-internal; from-relative; future; type-checking-branch; try-branch; function-body-recorded; class-body-recorded; nested-branch-in-function; with-or-loop-block-not-recorded | 100% | record name·line이 명세와 같음 | pytest |
| V02 | F03, C03 | `PythonModuleIndex.is_internal` | unit | decision table | C03 표 각 name | 100% | 표와 같은 bool | pytest |
| V03 | F04, C04 | Kotlin analyzer file node metadata, `kotlin_is_internal` | unit | equivalence partitioning | external-fqn; internal-fqn; internal-star; external-star; prefix-mismatch(`com.ex.Shared`); parent-of-repo-package(`com.ex`) | 100% | 기록 집합이 명세와 같음 | pytest |
| V04 | F05, C05, C06 | TS analyzer module metadata, `typescript_package_name` | unit | equivalence partitioning + boundary value analysis (2-value) | static-scoped; type-only; export-from; require-node; dynamic-import; relative; absolute; C06 표 각 행 | 100% | name·specifier·dynamic·line | pytest |
| V05 | F06, C07–C11 | `parse_tsconfig_aliases`, `is_typescript_alias`, analyzer coverage | unit | decision table (alias) + syntax testing (parser) | C07 표 각 specifier; C08 표 각 specifier; jsonc-line-comment; jsonc-block-comment; slash-in-string; trailing-comma; C10 각 입력; invalid-coverage-record; missing-file; missing-compilerOptions | 100% | bool·ValueError·coverage 기록 유무 | pytest |
| V06 | F01, F02, C12 | `normalize_external_imports` | unit | equivalence partitioning | duplicate; ordering-by-name-line; specifier-order; dynamic-order; empty-to-no-key | 100% | 목록이 명세 순서와 같음 | pytest |
| V07 | F07, C13 | file 투영 | unit/integration; 합성 snapshot 또는 소형 repo | scenario testing | union-two-nodes; details-keep-key(file 모드 details = symbol 모드 node); boundary-no-key; symbol-mode-keeps-key; no-records-no-key | 100% | metadata 유무와 내용 | pytest |
| V08 | F08, C14, C15, Q05, Q08 | loader | unit; tmp_path YAML | syntax testing | C14 각 행; C15 정규화 항목 각각(sort, dedup, merge-same-from, to-and-to_external); python-object-tag; 2a-file-unchanged | 100% | 오류와 메시지 원인, 정상 필드 | pytest |
| V09 | F09, F10, F11, C16–C19 | 외부 위반 판정·candidate 형식 | unit; `analyze_structure` 합성 FileArchitecture | decision table | (forbid match, allow absent); (forbid match, allow match); (forbid match, allow no-match); (no forbid match, allow no-match); (no forbid match, allow match); group-prefix-vs-literal; unassigned-file; layer-not-in-allow_external; no-imports; static+dynamic; dynamic-only; candidate-fields | 100% | candidate 수·id·target·metrics·evidence·structure가 독립 oracle과 같음 | pytest |
| V10 | F12, C20 | coverage | unit | equivalence partitioning | with-external-rules-keys; counts; total-violation-count; without-external-rules-same-keys | 100% | coverage dict | pytest |
| V11 | F13, F16, Q04, Q07, C21, C28, C30 | 호환·결정성 | integration; 5개 fixture | scenario testing | bottleneck-byte-equal ×5; architecture-canonical-equal file ×5; architecture-canonical-equal symbol ×2; has-external-imports ×5; determinism-hashseed; 2a-rules-equal | 100% | `tests/external_rules_evidence/base_manifest.json`(main이 base_commit에서 생성)과 비교 | pytest |
| V12 | F03–F05, C22–C25 | 실제 fixture | integration(subprocess CLI) | scenario testing | realworld-example-violations; official-template-backend-root; nestjs-records; nowinandroid-records | 100% | 명세에 적힌 record·위반 존재/부재 | pytest |
| V13 | F14, Q06, Q08, C26, C27 | report·HTML | unit + end-to-end(Playwright) | scenario testing | validator-accepts; forbid-external-reason; allow-external-reason; internal-reason-unchanged; hostile-specifier-text | 100% | DOM text, dialog 미발생 | pytest browser |
| V14 | Q02, Q03, C29 | 분량·시간 | integration(기본 실행) | boundary value analysis (2-value) | size-ratio ×5; bottleneck-ratio-realworld; synthetic-time | 100% | 상한 이하 | pytest |
| V15 | Q09 | import 경계 | unit | syntax testing | rules-module-imports; core-helper-imports | 100% | AST import 목록 | pytest |
| V16 | Errors | 경계 사례 | unit | error guessing | 추정 결함: relative-import-recorded-as-external(상대 import가 repo에 없을 때 외부로 기록); namespace-root-misclassified(`backend.app` root에서 `app.*`를 외부로 기록); star-key-swallows-all(tsconfig `*` key가 모든 bare specifier를 alias로 만듦); group-name-without-prefix-expanded(접두어 없는 entry를 group으로 해석); undefined-group-accepted(`group:missing`을 조용히 무시); empty-allow-external-list(빈 목록에서 위반 0); coverage-keys-leak(외부 규칙 없을 때 F12 key 추가) | none — experience-based | 명세대로 | pytest |
| V17 | Q10 | branch coverage | Test command | branch testing (coverage.py) | 두 module의 branch | ≥ 90% | coverage report 통과 | Test command |
| V18 | Q07 | fuzz | main 실행 | random testing | loader-20000; tsconfig-20000; package-name-20000 | 100%(예산 전부) | 허용 예외 외 0, property 위반 0 | main harness, ledger |

# Assumptions and Defaults
| id | decision | evidence and uncertainty | brief v<n> — approved / vetoed → <answer> / user answer |
| --- | --- | --- | --- |
| A01 | 규칙 형식 forbid `to_external` + `allow_external` + `external` group | 사용자 선택 | user answer |
| A02 | TS 루트 tsconfig `paths` alias 제외, `extends` 미추적, JSONC 주석 제거, 실패 시 coverage 경고 | 사용자 선택 | user answer |
| A03 | `external_imports` 항상 기록 | 사용자 선택 | user answer |
| A04 | stdlib 구분 안 함 | 언어 버전마다 목록이 다름. 패턴으로 거름 | 계획 기본값 — approved |
| A05 | Python 함수·class body 안 import도 기록, `with`/`for`/`while`/`match` 블록은 제외 | v1의 "함수 안 미수집"은 analyzer 동작을 잘못 파악한 전제(`symbols.py:278`, `:312`가 body를 재귀 방문)였다. 이제 analyzer 수집 범위와 같다 | user answer (v2) |
| A06 | group 참조는 `group:` 접두어, 정의되지 않은 group 참조는 오류(계획의 "group과 pattern 혼동은 오류"를 대체) | 계획 규칙은 `fastapi` 같은 정확한 이름 pattern을 오류로 만든다. group 우선 해석은 오타·이름 충돌이 조용히 위반을 놓친다 | user answer |
| A07 | Python 내부 판정은 `__init__.py` 없는 디렉터리를 import root로 보는 규칙(F03) | fastapi-official-template은 `backend/app`에서 `from app...`을 쓴다. PEP 420 namespace package가 많은 repo에서는 내부로 과하게 판정될 수 있다 | brief v1 — approved |
| A08 | TS `baseUrl`도 alias로 본다(F06 b) | baseUrl만 쓰는 repo는 내부 import가 전부 외부로 잡힌다. 사용자는 `paths`만 선택했으므로 확장이다 | user answer |
| A09 | 외부 위반 단위는 (file, name). Python은 dotted 이름 전체라 `asyncpg.connection`과 `asyncpg.pool`은 별개 candidate | 정밀하지만 개수가 늘 수 있다. R1에서 측정 | user answer |
| A10 | 외부 candidate structure에는 `to_layer`가 없고 `to_external`을 둔다 | layer 이름 `external`과 충돌 방지 | brief v1 — approved |
| A11 | Q02 architecture ≤ 1.05, bottleneck ≤ 1.25, Q03 5 s, Q10 90% | 측정치 기반(예상 증가 1–2%) | brief v1 — approved |
| A12 | 외부 규칙이 없으면 coverage key 추가 안 함, rules version 1 유지 | 2a 규칙 file과 결과 호환 | brief v1 — approved |

# Traceability
| requirement id | Case ids | obligation ids | evidence procedure |
| --- | --- | --- | --- |
| F01, F02 | C12 | V06 | pytest |
| F03 | C01–C03, C23 | V01, V02, V12, V16 | pytest |
| F04 | C04, C25 | V03, V12 | pytest |
| F05 | C05, C06, C24 | V04, V12, V18 | pytest, fuzz |
| F06 | C07–C11 | V05, V16, V18 | pytest, fuzz |
| F07 | C13 | V07 | pytest |
| F08 | C14, C15, C30 | V08, V18 | pytest, fuzz |
| F09–F11 | C16–C19 | V09, V16 | pytest |
| F12 | C20 | V10, V16 | pytest |
| F13, F16 | C21, C28, C30 | V11 | pytest + base manifest |
| F14 | C26, C27 | V13 | Playwright, R2 |
| F15 | C22 | V08, V12 | pytest, R1 |
| Q01–Q11 | C29 | V01–V18 | pytest, R1, R2, fuzz |

# Workflow Control
| item | value |
| --- | --- |
| correction batches used | 3 |
| verifier invocations | 2 |
| open finding ids | none |

Audit state (one entry per obligation; retain prior decisions in the execution ledger):
| obligation id | spec version | evidence references and revision | accepted / open / invalidated / pending | rationale and mutation outcome | dependencies and reopening evidence |
| --- | --- | --- | --- | --- | --- |
| V02, V03, V06, V07, V08, V09, V10, V11, V13, V15, V16, V17, V18 | 3 | test files at batch 3; Test command run 5; fuzz; hand H01–H16 | accepted (verifier 1, retained by verifier 2) | H01, H03, H07–H12 killed | batch 3 changes additive; A-01 revert consistent |
| V01, V04, V05, V12, V14 | 3 | batch 3 tests; Test command run 5; H13–H16 killed; r1-top-names.json | accepted (verifier 2) | F-01–F-06 closed; H02, H04–H06, H13–H16 killed | none |

Execution ledger (append attempts; preserve failed approaches):
| attempt | finding / failure signature | cause hypothesis | changed approach / new evidence | result / disposition |
| --- | --- | --- | --- | --- |
| 1 | Test command run 1: 23 failed / 2102 passed, branch 100% | — | 분류 아래 | correction batch 1 |
| 1 | `test_V03_C04_kotlin_analyzer_records`: line 2 ≠ 3 | implementation defect (verified: `kotlin/analyzer.py` 정규식 `^\s*import`가 앞 빈 줄의 개행을 먹어 match.start()가 한 줄 앞) | v3 F01 명시, implementer가 record line만 교정 | pending |
| 1 | `test_V12_C23`: `app.api.deps` 외부로 기록 | spec gap (verified: `backend/app/api/deps.py`가 Python 3.14 문법이라 3.12에서 파싱 실패, module 목록에서 빠짐) | v3 F03: 파싱 실패 file도 modules에 포함 | pending |
| 1 | `test_file_analysis_cli::test_V07_combinations_preserve_semantic_details` ×5: details ≠ symbol | spec defect (F07이 기존 불변 조건과 충돌) | v3 F07: details 유지, 사용자 재-brief "details에도 남김" | pending |
| 1 | `test_file_analysis_cli::test_V01` ×4, `test_analysis_coverage_reporting::test_V05`, `test_nestjs_quality::test_O11` ×8: golden 불일치 | expected change (verified for V01·V05: `external_imports` 제거 plugin으로 통과) | v3 Tests 경로에 golden 비교 전 key 제거만 허용 | pending |
| 1 | `test_V12_C25_nowinandroid_records`: snapshot에 없는 repo package import가 외부로 기록 | test defect (verified: fixture sparse checkout, git ls-files 310 `.kt` 중 일부만 존재) | v3 C25 명확화 | pending |
| 1 | `test_V14_C29`: 7.76 s − 0.20 s > 5.0 | test input defect/spec gap (verified profile: 562,025 외부 candidate, file당 28개 위반; `_candidate`·정렬이 선형 비용) | v3 C29 위반 밀도 ≤ 10% | pending |
| 1 | `test_V05_invalid_coverage_record[filesystem]`: KeyError `analysis_coverage` | test defect (verified: `attach_coverage`는 snapshot이 있을 때만 coverage를 붙임) | v3 F06 명시 | pending |
| 2 | Test command run 2: 2 failed / 2115 passed, branch 100%. `test_V12_C23`: oracle `ref_python_external_names`가 3.14 문법 file에서 SyntaxError | test defect (verified, traceback) | correction batch 2: oracle이 파싱 실패 file은 import 수집에서 건너뛰되 module 목록에는 포함 | pending |
| 2 | `test_V12_C25`: `startswith('com.google.samples.apps.nowinandroid')` 전부 부재 assertion이 남음 | test defect (verified: v3 C25 반영 누락) | correction batch 2 | pending |
| 3 | Test command run 3: 2 failed (`test_architecture_rules_integration::test_V11_synthetic_time` 24.6−5.0 s, `test_report_modal::test_V04…[connection]`) | environment (verified: load average 56.8 during run; same tests pass in run 2 and in an isolated rerun at load 6.5: 5 passed) | rerun at low load | not a defect |
| 3 | Test command run 4: rc 0, 2117 passed, branch 100% (both modules) | — | — | pass |
| 3 | fuzz: loader 20,000 crash 0 (accepted 1215); tsconfig 20,000 violations 0; package_name first run 2092 violations, all inputs starting with `/` | main harness defect (verified: F05 excludes `.`/`/` specifiers before naming; in-domain recheck 0 violations) | domain restricted to non-`.`/`/` specifiers, full budget rerun | 20,000 execs, 0 violations |
| 3 | R1 `tests/external_rules_evidence/size.json`: architecture ratio 1.0118–1.0142 (≤1.05), realworld rules bottleneck ratio 1.0057 (≤1.25); external violations db→fastapi, api→asyncpg.connection, api→asyncpg.pool; nowinandroid top names include absent sparse-checkout repo packages (C25 expected) | — | review | pass |
| 3 | R2 `tests/external_rules_evidence/r2-fastapi-realworld.png`: `경계 규칙 위반 · db → fastapi · 외부 금지 규칙` | — | review | pass |
| 4 | hand mutations H01–H12 (`tests/external_rules_evidence/hand-mutations.json`): 12/12 killed | — | — | pass |
| 4 | mutation tool (`tests/external_rules_evidence/mutation-tool.json`): pool 209, 30 executed, 26 killed, 4 survived (13.3% < 40%). triager: M21 equivalent, M22 equivalent (main recheck: `find` from a `/` position never returns 0; `split("/", n)[0]` identical for n ≥ 1), M24 declared (empty `/**/` comment), M08 undeclared (2a `to: []` rejection) | M08: main resolves — 2a requirement; re-injected and killed by `tests/test_architecture_rules.py::test_V01_C12_table_row[forbid-to-empty-list]` (outside the tool command). M24: V05 evidence gap | M24 → correction batch 3 | pending |
| 4 | verifier 1: retry, F-01 multi-line line semantics (V01/V04), F-02 deterministic unparseable-file test (V01/V12), F-03 baseUrl segment semantics (V05), F-04 analyzer-level C10 rows (V05), F-05 R1 top-20 review artifact (V14), F-06 alias exclusion on dynamic/export paths (V04/V05); advisories A-01–A-05 | evidence gaps (verified by main probe: implementation already behaves per spec on every listed input — statement lines, alias on dynamic/export, baseUrl `app/other`/`utils/foo` internal and `src2/x` external, broken module internal, 4 schema-invalid tsconfigs proceed) | correction batch 3 (tests F-01–F-04, F-06, A-01, A-02, M24); F-05 main: `tests/external_rules_evidence/r1-top-names.json`; A-03 main: harness copied to `tests/external_rules_evidence/fuzz/` | pending |
| 5 | correction batch 3 landed (tests only): F-01 multi-line Python/TS line tests, F-02 deterministic unparseable module/package tests, F-03 baseUrl segment/stem rows incl. root baseUrl, F-04 analyzer-level C10 ×5, F-06 alias exclusion on require/import()/export-from, A-01 exact example `forbid`, A-02 undefined `from` with to_external only, M24 `/**/` and `/***/` C09 rows | — | re-mutation H13 (M24) killed by `test_V05_C09_jsonc_syntax[jsonc-empty-block-comment]`; H14 alias only static killed by `test_V04_F06_alias_exclusion_applies_to_non_static_forms`; H15 unparseable excluded killed by `test_V01_F02_unparseable_module_still_counts_as_internal`; H16 baseUrl whole-specifier killed by `test_V05_C08_base_url_table[C08-app/x]` | 16/16 hand mutations killed |
| 5 | Test command run 5: rc 0, 2132 passed, branch 100% | — | — | pass |
| 5 | verifier 2: pass, blocking 0; A-01–A-03 resolved; A-04 (nestjs oracle loose upper bound), A-05 (Kotlin `as` alias/nested star) remain advisory | — | not applied | advisory (non-blocking) |

# Version Log
## v1
- 초안. 계획 Phase 2b, 사용자 답변(A01–A03, brief에서 A06 `group:` 접두어, A08 baseUrl 포함, A09 (file, name) 단위), 측정: fixture 외부 import 문 수(183–855), base architecture JSON 크기, fastapi-realworld layer별 외부 import(db→fastapi 1 file, api→asyncpg 1 file, domain은 pydantic·typing·datetime만), fastapi-official-template `backend/app` layout.
## v2
- [intent-mismatch] F03·C02·V01·Scope·A05: Python 함수·class body 안 import도 기록(`with`/`for`/`while`/`match` 블록은 제외). 근거: main이 `language_analyzers/python/symbols.py:278`, `:312`를 확인해 보니 analyzer가 body를 재귀 방문한다. 계획·v1의 전제가 틀렸다. 사용자 재-brief 답변 "기록함".
- Tests 경로에 `tests/test_architecture_rules_integration.py` 추가(2a 테스트 조정만). 근거: test-implementer 보고 — `BAD_RULES['external']`의 "not supported" 기대, 예제 profile coverage key 집합, 외부 candidate의 `to_layer` KeyError.
- 계약 명확화(test-implementer challenge): `path_keys`는 `*` 포함 모든 key; `to_external`만 있는 forbid 항목은 내부 `forbid`에 entry 없음; `allow_external: {}`는 외부 규칙 없음과 같음(F12 판정은 파싱된 mapping의 key 유무); C27은 공개 함수로 렌더링. Q09는 문자 그대로(base의 `analysis/architecture_rules.py`는 `language_analyzers`를 import하지 않음).
## v3
- [intent-mismatch] F07: file 모드 details node에 `external_imports` 유지(boundary 복사본만 제거). 근거: 기존 불변 조건 테스트 `tests/test_file_analysis_cli.py::test_V07_combinations_preserve_semantic_details` 5건 실패. 사용자 재-brief 답변 "details에도 남김". V07 coverage item details-no-key → details-keep-key.
- F01: record line은 문 시작 줄(Kotlin 기존 정규식 off-by-one은 record에 쓰지 않음). F03: 파싱 실패 `.py`도 modules·packages에 포함. F06: coverage는 snapshot 모드에서만. C25: sparse fixture 기준 명확화. C29: 위반 밀도 ≤ 10%. Tests 경로에 golden 비교 file 3개(`external_imports` key 제거만). 근거: Test command run 1 실패 분류(ledger attempt 1).
