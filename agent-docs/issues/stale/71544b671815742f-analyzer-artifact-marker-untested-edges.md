# analyzer_artifact 판정의 미검증 경계

`repository/scan.py`의 `_is_agent_view_artifact`는 저장소에 들어 있는 이 분석기의 이전 산출물을 스냅샷에서 `analyzer_artifact`로 제외한다. JSON 판정은 텍스트 전체에서 `"schema_version": "2"|"3"`(콜론 뒤 공백 0/1)과 `"occurrence_store"` 또는 `"query_nodes"`를 함께 찾고, HTML 판정은 앞 65536자에서 `agent-view-v3-payload` 또는 `id="agent-view-data"`를 찾는다.

`tests/test_repository_scan.py`는 위 네 표식의 양성 사례와 표식 한쪽만 있는 음성 사례만 검사한다. 다음은 테스트가 없다.
- HTML 표식이 65536자 이후에 있으면 산출물로 보지 않는 경계
- schema_version이 "2"/"3"이 아닌 값("1", "4")의 음성 사례

같은 로직의 사본이 `language_analyzers/core/enrichment.py`의 `_is_agent_view_artifact`에도 있다(config key 수집에서 산출물 건너뛰기).

사용자 결정(워크플로 3dfc6bf47f6a3947 후속, handoff 5e5f4c6a7336658f 항목 4)으로 범위 밖에 둔다. 판정 규칙이 agent_view 출력 형식에 묶여 있어 방향 전환 중 바뀔 가능성이 높기 때문이다.

## 무효화 조건
다음 중 하나가 일어나면 이 이슈를 stale로 옮긴다.
- agent_view 산출물(schema_version 2/3 JSON, `agent-view-v3-payload`/`agent-view-data` HTML) 생성이 제거되고 `_is_agent_view_artifact`와 `analyzer_artifact` 제외 사유가 삭제됨
- 새 출력 형식에 맞춰 판정 표식이 교체됨(이 경우 새 표식 기준으로 경계 테스트 필요 여부를 다시 판단)
- 위 두 경계에 대한 테스트가 추가됨
