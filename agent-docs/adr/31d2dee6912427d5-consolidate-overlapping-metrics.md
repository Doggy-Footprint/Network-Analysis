# 겹치는 노드 지표 통합

Status: Accepted

## Context
같은 가중 엣지에서 PageRank·HITS·degree·fan·hop_2/3을 함께 내보내 순위 정보가 중복됐다. 노드 지표는 16개였고, bottlenecks 순위도 12개 키로 같은 정보를 반복했다.

## Decision
HITS(hub_score, authority_score), degree_centrality, hop_3_token_cost, hop_2_node_count, hop_3_node_count를 제거한다.

- authority_score는 PageRank처럼 들어오는 연결 기준의 중심성이다.
- hub_score는 나가는 가중 연결(weighted_fan_out)과 겹친다.
- degree_centrality는 (fan_in + fan_out) / 2(n−1)이므로 순위가 fan_in + fan_out 순위와 같다.
- hop_3_token_cost의 3-hop 집합은 hop_2 집합을 포함하고, node_count 지표는 보고서와 순위에서 쓰지 않는다.

남는 지표는 token_cost, effective_token_cost, pagerank, betweenness_centrality, weighted_centrality_cost, fan_in, fan_out, weighted_fan_in, weighted_fan_out, hop_2_token_cost다. 스키마는 bottlenecks.v6(symbol)과 bottlenecks.v7(file)이며 versions.analysis는 "4"다.

## Alternatives
- 모든 지표 유지: 같은 정보를 다른 이름의 순위로 반복 노출하므로 기각했다.

## Consequences
- (+) 노드 지표가 16개에서 10개로 줄고, HITS 반복 계산과 3-hop 집합 계산이 없어진다.
- (−) 이전 스키마(bottlenecks.v4/v5) JSON은 새 보고서로 렌더링되지 않는다.
