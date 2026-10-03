# 분류별 순위 HTML 테스트의 지표 패널 부분 문자열 판정

`report/bottlenecks/generate.py`는 `rankings_by_category`의 분류마다 `<div data-category="<분류>">`를 만들고, 그 안에 지표별 패널(`<h3>지표명</h3>`)을 둔다.

`tests/test_category_rankings_v3.py`의 V6 테스트는 각 div에 12개 지표명이 있는지를 `metric in div` 부분 문자열로 검사한다. `fan_in`은 `weighted_fan_in`의, `fan_out`은 `weighted_fan_out`의 부분 문자열이므로 분류 div에서 `fan_in`/`fan_out` 패널을 빼도 테스트가 통과한다. 뮤테이션으로 확인했다(25 passed). 두 지표의 항목 목록을 서로 바꾸는 결함은 검사하지 않았다.

워크플로 3ea9cf8886ee409f(spec-log, status limit)의 verifier 2 finding B2이며, 사용자 결정으로 이슈로만 남긴다.

## 무효화 조건
다음 중 하나가 일어나면 이 이슈를 stale로 옮긴다.
- V6 테스트가 지표 패널을 정확히 매칭하도록 바뀌어 `fan_in`/`fan_out` 패널 누락이 실패로 잡힘
- 분류별 순위 HTML 섹션이 제거되거나 패널 구조가 바뀜(새 구조 기준으로 다시 판단)
