(() => {
    'use strict';
    window.ReportGraph = null;
    const $ = id => document.getElementById(id);
    const el = (tag, text, cls) => {
        const n = document.createElement(tag);
        if (text !== undefined) n.textContent = text;
        if (cls) n.className = cls;
        return n;
    };
    const finite = v => typeof v === 'number' && Number.isFinite(v);
    const format = v => finite(v) ? new Intl.NumberFormat('ko-KR', {
        maximumSignificantDigits: 5
    }).format(v) : '—';
    const cmp = (a, b) => a < b ? -1 : a > b ? 1 : 0;
    const definitions = {
        pagerank: ['참조가 모이는 곳', '다른 대상에서 참조받는 상대적 중심성', '상대값'],
        betweenness_centrality: ['경로를 잇는 곳', '대상 사이의 최단 경로를 중개하는 정도', '상대값'],
        hop_2_token_cost: ['주변 코드가 넓은 곳', '연결 두 단계 이내 주변 코드의 할인된 토큰 합', '추정 토큰'],
        weighted_centrality_cost: ['중심에 있는 큰 코드', 'PageRank × 할인된 코드 토큰 수', '가중 토큰'],
        fan_in: ['들어오는 연결이 많은 곳', '이 대상을 참조하는 직접 연결 대상 수', '대상'],
        fan_out: ['나가는 연결이 많은 곳', '이 대상이 참조하는 직접 연결 대상 수', '대상'],
        hub_score: ['Hub', '참조하는 쪽의 중심성', '상대값'],
        authority_score: ['Authority', '참조받는 쪽의 중심성', '상대값'],
        degree_centrality: ['Degree', '전체 크기로 정규화한 직접 연결 정도', '상대값'],
        weighted_fan_in: ['가중 Fan-in', '들어오는 연결 대상별 유효 가중치 합', '가중 연결'],
        weighted_fan_out: ['가중 Fan-out', '나가는 연결 대상별 유효 가중치 합', '가중 연결'],
        hop_3_token_cost: ['3-hop 주변 규모', '세 단계 이내 주변 코드의 할인된 토큰 합', '추정 토큰'],
        token_cost: ['코드 규모', '문자 기반 코드 토큰 추정', '추정 토큰'],
        effective_token_cost: ['할인된 코드 규모', '생성·외부 코드를 할인한 토큰 추정', '추정 토큰'],
        identifier_file_count: ['식별자 출현 파일', '이름의 마지막 식별자가 등장하는 파일 수', '파일']
    };
    const core = Object.keys(definitions).slice(0, 6);
    const kinds = {
        unresolved_boundary: ['정적 분석 미확정 참조', '정적 분석으로 참조·호출 대상을 확정하지 못했거나, 실행 중 해석이 필요한 부분입니다.'],
        evidence_spread: ['근거 분산', '참조 근거가 여러 파일 또는 넓은 줄 범위에 퍼져 있습니다.'],
        large_node: ['큰 노드', '소스 범위가 설정한 줄 수 임계값을 넘습니다.']
    };
    const categoryLabels = {
        all: '전체',
        production: '운영 코드',
        test: '테스트',
        generated: '생성 코드',
        vendored: '외부 코드',
        unknown: '미분류'
    };
    let data, arch, bottlenecks, network, nodes, nodeMap, metrics, candidates, byTarget, incident, category, page = 0,
        relationshipPage = 0,
        selected, relations = [];
    const categorySelect = $('category-filter').querySelector('select'),
        sortSelect = $('metric-sort').querySelector('select'),
        kindSelect = $('candidate-kind-filter').querySelector('select'),
        limitSelect = $('list-limit').querySelector('select');

    function rawDetails(title, value, parent) {
        const d = el('details');
        d.append(el('summary', title));
        let built = false;
        d.addEventListener('toggle', () => {
            if (d.open && !built) {
                d.append(el('pre', typeof value === 'string' ? value : JSON.stringify(value, null, 2)));
                built = true;
            }
        });
        parent.append(d);
        return d;
    }

    function nodeName(node) {
        const name = node.display_label || node.label || node.id;
        const path = node.span?.file_path;
        return ['file', 'module', 'package'].includes(node.category) && path && name === path ? path.replace(/\\/g, '/').split('/').pop() : name;
    }

    function button(node) {
        const b = el('button', undefined, 'node-button');
        b.dataset.nodeId = node.id;
        const label = el('span', undefined, 'node-label-block');
        label.append(el('span', nodeName(node), 'node-name'));
        label.append(el('span', node.span?.file_path || '소스 위치 없음', 'path'));
        b.append(label);
        b.addEventListener('click', () => selectNode(node.id));
        return b;
    }

    function badges(id, parent) {
        const ks = new Set((byTarget.get(id) || []).map(c => c.kind));
        for (const k of ks) parent.append(el('span', kinds[k]?.[0] || k, 'badge'));
    }

    function eligible() {
        if (arch) return nodes.filter(n => metrics[n.id] && (category === 'all' || data.categories[n.id] === category));
        if (category === 'all') return nodes.filter(n => metrics[n.id]);
        const ids = new Set(Object.values(network.rankings_by_category?.[category] || {}).flat().map(r => r.node_id));
        return nodes.filter(n => ids.has(n.id));
    }

    function sorted(rows, key) {
        return rows.slice().sort((a, b) => {
            const av = metrics[a.id]?.[key],
                bv = metrics[b.id]?.[key];
            return finite(av) && finite(bv) ? bv - av || cmp(a.id, b.id) : finite(av) ? -1 : finite(bv) ? 1 : cmp(a.id, b.id);
        });
    }

    function renderRepresentatives() {
        const host = $('representatives');
        host.replaceChildren();
        const available = eligible();
        for (const key of core) {
            const [name, desc, unit] = definitions[key], card = el('article', undefined, 'metric-card');
            card.dataset.metricGroup = key;
            card.append(el('h3', name), el('p', desc + ' · ' + unit));
            let rows = sorted(available.filter(n => finite(metrics[n.id]?.[key])), key);
            if (!rows.length) card.append(el('div', category === 'production' ? '운영 코드 결과가 없습니다. 코드 분류를 전환하세요.' : '표시할 지표가 없습니다.', 'empty'));
            else {
                if (rows.every(n => metrics[n.id][key] === 0)) card.append(el('div', '모든 값이 0입니다.', 'notice'));
                const list = el('div', undefined, 'representative-list');
                list.tabIndex = 0;
                list.setAttribute('role', 'region');
                list.setAttribute('aria-label', name + ' 상위 10개');
                for (const n of rows.slice(0, 10)) {
                    const b = button(n);
                    b.className = 'representative';
                    b.title = `${nodeName(n)}\n${n.span?.file_path || '소스 위치 없음'}`;
                    b.append(el('span', format(metrics[n.id][key]), 'value'));
                    list.append(b);
                }
                card.append(list);
            }
            host.append(card);
        }
    }

    function renderList() {
        const query = $('node-search').value.trim().toLocaleLowerCase(),
            key = sortSelect.value;
        let rows = eligible().filter(n => (`${n.label||''} ${n.display_label||''} ${n.span?.file_path||''} ${n.id}`).toLocaleLowerCase().includes(query) && (kindSelect.value === 'all' || (byTarget.get(n.id) || []).some(c => c.kind === kindSelect.value)));
        rows = sorted(rows, key);
        const matchingCount = rows.length;
        if (limitSelect.value === '100') rows = rows.slice(0, 100);
        page = Math.min(page, Math.max(0, Math.ceil(rows.length / 50) - 1));
        const host = $('node-list');
        host.replaceChildren();
        for (const n of rows.slice(page * 50, page * 50 + 50)) {
            const tr = el('tr');
            tr.dataset.nodeRow = n.id;
            const a = el('td');
            a.append(button(n));
            const b = el('td');
            badges(n.id, b);
            if (!b.childNodes.length) b.append(el('span', '—', 'muted'));
            tr.append(a, b, el('td', format(metrics[n.id]?.[key]), 'value'));
            host.append(tr);
        }
        if (!rows.length) {
            const tr = el('tr'),
                td = el('td', category === 'production' ? '결과가 없습니다. 코드 분류를 전환하거나 검색 조건을 바꾸세요.' : '검색 조건에 맞는 대상이 없습니다.', 'empty');
            td.colSpan = 3;
            tr.append(td);
            host.append(tr);
        }
        $('list-count').textContent = `${rows.length.toLocaleString('ko-KR')}개 표시 / 조건 일치 ${matchingCount.toLocaleString('ko-KR')}개 · 전체 ${nodes.filter(n=>metrics[n.id]).length.toLocaleString('ko-KR')}개 대상`;
        $('page-label').textContent = `${rows.length?page+1:0} / ${Math.ceil(rows.length/50)} 페이지`;
        $('page-prev').disabled = page === 0;
        $('page-next').disabled = (page + 1) * 50 >= rows.length;
        $('sort-heading').textContent = definitions[key]?.[0] || key;
    }

    function evidenceText(e) {
        if (typeof e === 'string') return e;
        if (!e) return '근거 없음';
        if (!e.path && !e.file_path) return JSON.stringify(e);
        return `${e.path||e.file_path||''}:${e.start_line??''}–${e.end_line??e.start_line??''}`;
    }

    function renderRelationships() {
        const host = $('relationship-list');
        host.replaceChildren();
        for (const edge of relations.slice(relationshipPage * 50, relationshipPage * 50 + 50)) {
            const row = el('div', undefined, 'relationship');
            row.dataset.relationshipRow = '';
            for (const id of [edge.from_id, edge.to_id]) {
                const n = nodeMap.get(id) || {
                    id
                };
                row.append(button(n));
                if (id === edge.from_id) row.append(el('span', ' → '));
            }
            row.append(el('div', `${edge.relation||'관계'} · ${edge.confidence||'static_certain'} · ${edge.resolution||'exact'}`));
            row.append(el('div', evidenceText(edge.evidence), 'path'));
            rawDetails('연결의 전체 근거와 다른 대상 후보', edge, row);
            host.append(row);
        }
        if (!relations.length) host.append(el('p', arch ? '직접 연결이 없습니다.' : '연결 데이터가 제공되지 않았습니다.', 'empty'));
        $('relationship-prev').disabled = relationshipPage === 0;
        $('relationship-next').disabled = (relationshipPage + 1) * 50 >= relations.length;
        $('relationship-count').textContent = `${relations.length}개 연결 · ${relations.length?relationshipPage+1:0} / ${Math.ceil(relations.length/50)} 페이지`;
    }

    function graph(id) {
        if (window.ReportGraph) {
            window.ReportGraph.destroy();
            window.ReportGraph = null;
        }
        const status = $('graph-status');
        status.dataset.shown = '0';
        status.dataset.omitted = '0';
        if (!arch) {
            status.textContent = '연결 탐색 불가: 아키텍처 데이터가 없습니다.';
            return;
        }
        const weights = bottlenecks?.edge_weights || {
            confidence: {
                static_certain: 1,
                static_inferred: .3,
                framework_inferred: .3,
                dynamic_required: .3
            },
            resolution: {
                exact: 1,
                unique_name: 1,
                ambiguous: .3,
                unresolved: .3
            }
        };
        const neighbors = new Map();
        for (const e of relations) {
            const other = e.from_id === id ? e.to_id : e.from_id;
            if (other === id || !nodeMap.has(other)) continue;
            const weight = Math.min(weights.confidence?.[e.confidence || 'static_certain'] ?? 1, weights.resolution?.[e.resolution || 'exact'] ?? 1);
            const entry = neighbors.get(other) || {
                weight: -Infinity,
                incoming: false,
                outgoing: false
            };
            entry.weight = Math.max(entry.weight, weight);
            entry.incoming ||= e.to_id === id;
            entry.outgoing ||= e.from_id === id;
            neighbors.set(other, entry);
        }
        const chosen = [...neighbors].sort((a, b) => b[1].weight - a[1].weight || (finite(metrics[b[0]]?.fan_in) ? metrics[b[0]].fan_in : 0) - (finite(metrics[a[0]]?.fan_in) ? metrics[a[0]].fan_in : 0) || cmp(a[0], b[0])).slice(0, 30);
        status.dataset.shown = String(chosen.length);
        status.dataset.omitted = String(neighbors.size - chosen.length);
        status.textContent = `직접 이웃 ${chosen.length}개 표시 · ${neighbors.size-chosen.length}개 생략 · 분류 필터와 관계없이 연결 표시`;
        const elements = [{
                data: {
                    id,
                    label: nodeMap.get(id).display_label || nodeMap.get(id).label || id,
                    center: true
                },
                position: {
                    x: 0,
                    y: 0
                }
            }],
            groups = new Map(),
            ids = new Set(chosen.map(([key]) => key));
        const sideCounts = {
            incoming: 0,
            outgoing: 0,
            both: 0
        };
        const totals = {
            incoming: 0,
            outgoing: 0,
            both: 0
        };
        for (const [, neighbor] of chosen) {
            totals[neighbor.incoming && neighbor.outgoing ? 'both' : neighbor.incoming ? 'incoming' : 'outgoing']++;
        }
        const compact = $('graph-container').clientWidth < 550;
        const cellWidth = compact ? 84 : 112;
        const cellHeight = compact ? 42 : 52;
        const gridColumns = side => compact ? (totals.incoming && totals.outgoing ? 2 : 3) : Math.max(1, Math.ceil(totals[side] / 5));
        for (const [key, n] of chosen) {
            const side = n.incoming && n.outgoing ? 'both' : n.incoming ? 'incoming' : 'outgoing';
            const index = sideCounts[side]++;
            const columns = side === 'both' ? (compact ? 4 : 6) : gridColumns(side);
            const rows = Math.ceil(totals[side] / columns);
            const column = index % columns;
            const row = Math.floor(index / columns);
            const position = side === 'both' ? {
                x: (column - (columns - 1) / 2) * cellWidth,
                y: Math.max(120, Math.ceil(Math.max(totals.incoming / gridColumns('incoming'), totals.outgoing / gridColumns('outgoing')) / 2) * cellHeight + 65) + row * cellHeight
            } : {
                x: (side === 'incoming' ? -1 : 1) * (cellWidth + column * cellWidth),
                y: (row - (rows - 1) / 2) * cellHeight
            };
            elements.push({
                data: {
                    id: key,
                    label: nodeMap.get(key).display_label || nodeMap.get(key).label || key
                },
                position
            });
        }
        $('graph-container').style.height = compact && chosen.length > 15 ? '520px' : '';
        for (const e of relations) {
            if (e.from_id === e.to_id || !ids.has(e.from_id === id ? e.to_id : e.from_id)) continue;
            const key = JSON.stringify([e.from_id, e.to_id]);
            if (!groups.has(key)) groups.set(key, []);
            groups.get(key).push(e);
        }
        let i = 0;
        for (const list of groups.values()) elements.push({
            data: {
                id: `edge:${i++}`,
                source: list[0].from_id,
                target: list[0].to_id,
                label: list.length > 1 ? String(list.length) : list[0].relation,
                relations: list
            }
        });
        try {
            window.ReportGraph = cytoscape({
                container: $('graph-container'),
                elements,
                layout: {
                    name: 'preset',
                    fit: true,
                    padding: 35
                },
                style: [{
                    selector: 'node',
                    style: {
                        'label': 'data(label)',
                        'background-color': '#d6e9e3',
                        'color': '#183e36',
                        'shape': 'roundrectangle',
                        'width': compact ? 72 : 98,
                        'height': compact ? 30 : 36,
                        'font-size': compact ? 12 : 13,
                        'text-wrap': 'ellipsis',
                        'text-max-width': compact ? 66 : 92,
                        'text-valign': 'center'
                    }
                }, {
                    selector: 'node[center]',
                    style: {
                        'background-color': '#126d64',
                        'color': 'white'
                    }
                }, {
                    selector: 'edge',
                    style: {
                        'curve-style': 'bezier',
                        'target-arrow-shape': 'triangle',
                        'width': 1.5,
                        'line-color': '#94b8ad',
                        'target-arrow-color': '#94b8ad',
                        'label': '',
                        'font-size': 9,
                        'color': '#657780'
                    }
                }, {
                    selector: 'edge:selected, edge.hovered',
                    style: {
                        'label': 'data(label)',
                        'text-background-color': '#fafcfb',
                        'text-background-opacity': 1,
                        'text-background-padding': 3
                    }
                }],
                minZoom: .15,
                maxZoom: 3
            });
            window.ReportGraph.on('tap', 'node', event => selectNode(event.target.id()));
            window.ReportGraph.on('mouseover', 'edge', event => event.target.addClass('hovered'));
            window.ReportGraph.on('mouseout', 'edge', event => event.target.removeClass('hovered'));
            window.ReportGraph.on('tap', 'edge', event => {
                const host = $('grouped-edge-detail');
                host.replaceChildren(el('h3', '묶인 연결의 개별 근거'));
                for (const e of event.target.data('relations')) host.append(el('pre', JSON.stringify(e, null, 2)));
            });
        } catch (error) {
            status.classList.add('error');
            status.textContent = `그래프를 초기화할 수 없습니다: ${error.message}. 아래 연결 목록을 확인하세요.`;
            window.ReportGraph = null;
        }
    }

    function candidateReason(c) {
        const m = c.metrics;
        if (c.kind === 'large_node') return `소스 범위 ${format(m.line_count)}줄 · 임계값 ${format(m.line_threshold)}줄`;
        if (c.kind === 'evidence_spread') return `근거 ${format(m.file_count)}개 파일 · 줄 범위 ${format(m.line_span)}줄 · 임계값 ${format(m.line_threshold)}줄`;
        return finite(m.unresolved_count) ? `미확정 참조 ${format(m.unresolved_count)}건` : '참조 대상을 확정하려면 추가 확인이 필요합니다.';
    }

    function candidateEvidence(c, host) {
        const evidence = Array.isArray(c.evidence) ? c.evidence : [c.evidence];
        if (c.kind !== 'evidence_spread') {
            for (const e of evidence) host.append(el('div', evidenceText(e), 'path'));
            return;
        }
        const files = new Map();
        for (const e of evidence) {
            const path = e?.path || e?.file_path || '위치 정보 없음';
            if (!files.has(path)) files.set(path, new Set());
            files.get(path).add(e?.start_line !== undefined ? `${e.start_line}–${e.end_line ?? e.start_line}` : evidenceText(e));
        }
        host.append(el('p', `${evidence.length.toLocaleString('ko-KR')}개 근거 · ${files.size.toLocaleString('ko-KR')}개 파일`, 'muted'));
        for (const [path, ranges] of [...files].slice(0, 3)) {
            const row = el('div', undefined, 'evidence-preview');
            row.append(el('div', path, 'path'));
            row.append(el('span', `${[...ranges].slice(0, 3).join(' · ')}${ranges.size > 3 ? ` · 외 ${ranges.size - 3}개 범위` : ''}`, 'muted'));
            host.append(row);
        }
        if (files.size > 3) host.append(el('p', `외 ${files.size - 3}개 파일 · 전체 위치는 아래 기록에서 확인하세요.`, 'muted'));
    }

    function selectNode(id) {
        const n = nodeMap.get(id);
        if (!n) return;
        selected = id;
        relationshipPage = 0;
        relations = incident.get(id) || [];
        const host = $('node-detail');
        host.replaceChildren();
        host.dataset.selectedNode = id;
        host.append(el('div', '03 / 대상 상세', 'eyebrow'), el('h2', n.display_label || n.label || id), el('p', n.span ? evidenceText(n.span) : '소스 위치 정보 없음', 'path'));
        const values = el('div', undefined, 'metrics');
        for (const key of Object.keys(definitions)) {
            const box = el('div', undefined, 'metric-value');
            box.append(el('span', definitions[key][0]), el('strong', format(metrics[id]?.[key])));
            values.append(box);
        }
        host.append(values);
        host.append(el('h3', '검토 근거'));
        const cs = byTarget.get(id) || [];
        if (!cs.length) host.append(el('p', bottlenecks ? '발견된 후보 없음' : '후보 데이터가 제공되지 않았습니다.', 'muted'));
        for (const c of cs) {
            const box = el('article', undefined, 'candidate');
            box.append(el('h3', kinds[c.kind]?.[0] || c.kind), el('p', kinds[c.kind]?.[1] || ''), el('p', candidateReason(c)));
            candidateEvidence(c, box);
            rawDetails('후보의 전체 기록', c, box);
            host.append(box);
        }
        rawDetails('전체 지표 · 식별자 출현 컨텍스트', metrics[id] || {}, host);
        rawDetails('심볼 · 시그니처 · 문서 · 플래그 · 메타데이터', n, host);
        const gh = el('div', undefined, 'graph-head');
        gh.append(el('h3', '직접 연결'));
        const controls = el('div', undefined, 'graph-controls');
        for (const [key, text, action] of [
                ['graph-fit', '화면 맞춤', () => window.ReportGraph?.fit(undefined, 35)],
                ['graph-zoom-in', '확대', () => window.ReportGraph?.zoom(window.ReportGraph.zoom() * 1.2)],
                ['graph-zoom-out', '축소', () => window.ReportGraph?.zoom(window.ReportGraph.zoom() / 1.2)]
            ]) {
            const b = el('button', text);
            b.id = key;
            b.onclick = action;
            controls.append(b);
        }
        gh.append(controls);
        host.append(gh);
        const gs = el('p');
        gs.id = 'graph-status';
        gs.setAttribute('role', 'status');
        const gc = el('div');
        gc.id = 'graph-container';
        gc.setAttribute('aria-label', '선택 대상의 직접 이웃 그래프');
        host.append(gs, gc);
        const ge = el('div');
        ge.id = 'grouped-edge-detail';
        host.append(ge, el('h3', '전체 연결과 근거'));
        const rl = el('div');
        rl.id = 'relationship-list';
        host.append(rl);
        const nav = el('nav', undefined, 'pagination');
        const prev = el('button', '이전');
        prev.id = 'relationship-prev';
        prev.onclick = () => {
            relationshipPage--;
            renderRelationships();
        };
        const next = el('button', '다음');
        next.id = 'relationship-next';
        next.onclick = () => {
            relationshipPage++;
            renderRelationships();
        };
        const count = el('span');
        count.id = 'relationship-count';
        nav.append(prev, count, next);
        host.append(nav);
        renderRelationships();
        graph(id);
        host.tabIndex = -1;
        host.focus({
            preventScroll: true
        });
        host.scrollIntoView({
            block: 'start'
        });
    }

    function appendix() {
        const host = $('appendix-content');
        host.append(el('p', '토큰은 문자 기반 추정치입니다. 소스 범위가 겹칠 수 있으므로 합계를 저장소 고유 텍스트 양이나 실제 LLM 사용량으로 해석하면 안 됩니다. 식별자 컨텍스트별 파일 수는 서로 겹칠 수 있습니다.'));
        for (const [label, value] of [
                ['스냅샷 · 제외 정책', bottlenecks?.snapshot],
                ['연결 가중치 · 줄 수 임계값', bottlenecks?.edge_weights],
                ['버전', bottlenecks?.versions],
                ['분석 범위', bottlenecks?.coverage],
                ['한계', bottlenecks?.limitations],
                ['Betweenness 계산 전략 · 표본 수', {
                    strategy: network.betweenness_strategy,
                    sample_size: network.betweenness_sample_size
                }],
                ['아키텍처 분석 메타데이터', arch?.stats]
            ])
            if (value !== undefined) rawDetails(label, value, host);
        for (const [key, col] of Object.entries(arch?.collections || {})) {
            const d = el('details');
            d.dataset.collectionKey = key;
            d.append(el('summary', `${col.label||key} · ${col.rows?.length||0}개`));
            let built = false;
            d.addEventListener('toggle', () => {
                if (!d.open || built) return;
                built = true;
                let p = 0;
                const rows = el('div'),
                    nav = el('nav', undefined, 'pagination'),
                    prev = el('button', '이전'),
                    next = el('button', '다음'),
                    count = el('span');
                const draw = () => {
                    rows.replaceChildren();
                    for (const row of (col.rows || []).slice(p * 50, p * 50 + 50)) {
                        const item = el('pre', JSON.stringify(row, null, 2));
                        item.dataset.collectionRow = '';
                        rows.append(item);
                    }
                    prev.disabled = p === 0;
                    next.disabled = (p + 1) * 50 >= (col.rows || []).length;
                    count.textContent = `${p+1} / ${Math.max(1,Math.ceil((col.rows||[]).length/50))}`;
                };
                prev.dataset.collectionPrev = '';
                next.dataset.collectionNext = '';
                prev.onclick = () => {
                    p--;
                    draw();
                };
                next.onclick = () => {
                    p++;
                    draw();
                };
                nav.append(prev, count, next);
                d.append(rows, nav);
                draw();
            });
            host.append(d);
        }
        const glossary = el('div');
        for (const [key, [name, desc, unit]] of Object.entries(definitions)) glossary.append(el('h3', name + ' · ' + key), el('p', desc + ' (' + unit + ')'));
        host.append(glossary);
    }
    try {
        data = JSON.parse($('report-data').textContent);
        arch = data.architecture;
        bottlenecks = data.bottlenecks;
        if ((!arch && !bottlenecks) || (arch && (!Array.isArray(arch.nodes) || !Array.isArray(arch.edges))) || (bottlenecks && (!bottlenecks.dependency_network || !Array.isArray(bottlenecks.candidates)))) throw new Error('보고서 데이터 구조가 올바르지 않습니다.');
        network = bottlenecks?.dependency_network || arch?.stats?.analysis || {};
        metrics = {
            ...(network.node_metrics || {})
        };
        for (const n of arch?.nodes || [])
            if (!metrics[n.id] && n.metadata?.analysis) metrics[n.id] = n.metadata.analysis;
        nodes = arch ? arch.nodes.slice() : Object.keys(metrics).map(id => ({
            id,
            label: id
        }));
        if (!arch) {
            const seen = new Set(nodes.map(n => n.id));
            for (const table of [network.rankings || {}, ...Object.values(network.rankings_by_category || {})])
                for (const [key, rows] of Object.entries(table))
                    for (const row of rows) {
                        if (!seen.has(row.node_id)) {
                            nodes.push({
                                id: row.node_id,
                                label: row.node_id
                            });
                            seen.add(row.node_id);
                        }
                        metrics[row.node_id] ||= {};
                        if (metrics[row.node_id][key] === undefined) metrics[row.node_id][key] = row.value;
                    }
        }
        nodeMap = new Map(nodes.map(n => [n.id, n]));
        candidates = bottlenecks?.candidates || [];
        byTarget = new Map();
        for (const c of candidates) {
            if (!byTarget.has(c.target)) byTarget.set(c.target, []);
            byTarget.get(c.target).push(c);
        }
        incident = new Map();
        for (const e of arch?.edges || []) {
            for (const id of new Set([e.from_id, e.to_id])) {
                if (!incident.has(id)) incident.set(id, []);
                incident.get(id).push(e);
            }
        }
        category = categorySelect.value;
        for (const [key, [name]] of Object.entries(definitions)) {
            const option = el('option', name + ' · ' + key);
            option.value = key;
            sortSelect.append(option);
        }
        sortSelect.value = 'pagerank';
        $('scope').textContent = `${arch?.project_path||'JSON 병목 보고서'} · ${data.framework_label||'정적 분석'} · ${bottlenecks?.snapshot?.file_count??'—'}개 스냅샷 파일 · ${network.node_count??nodes.length}개 노드 · ${network.edge_count??arch?.edges?.length??'—'}개 연결`;
        const counts = $('summary-counts');
        for (const [key, label] of Object.entries(categoryLabels).filter(([k]) => k !== 'all')) {
            const box = el('div', undefined, 'count');
            box.append(el('strong', arch ? String(nodes.filter(n => data.categories[n.id] === key).length) : '—'), el('span', label));
            counts.append(box);
        }
        for (const [key, [label]] of Object.entries(kinds)) {
            const box = el('div', undefined, 'count');
            box.append(el('strong', bottlenecks ? String(candidates.filter(c => c.kind === key).length) : '—'), el('span', label + ' 후보'));
            counts.append(box);
        }
        $('capabilities').textContent = !arch ? '아키텍처 데이터 없음: 분류별 전체 목록·소스 위치·연결 탐색을 제공할 수 없습니다. 제공된 순위는 일부 대상만 포함할 수 있습니다.' : !bottlenecks ? '후보 데이터가 제공되지 않았습니다. 아키텍처 지표와 연결만 표시합니다.' : !candidates.length ? '발견된 후보 없음. 지표와 연결 근거를 검토할 수 있습니다.' : '각 후보 종류의 측정값은 서로 다른 의미입니다. 후보 표시는 우선순위나 품질 판정이 아닙니다.';
        renderRepresentatives();
        renderList();
        categorySelect.onchange = () => {
            category = categorySelect.value;
            page = 0;
            renderRepresentatives();
            renderList();
        };
        sortSelect.onchange = kindSelect.onchange = limitSelect.onchange = () => {
            page = 0;
            renderList();
        };
        $('node-search').oninput = () => {
            page = 0;
            renderList();
        };
        $('page-prev').onclick = () => {
            page--;
            renderList();
        };
        $('page-next').onclick = () => {
            page++;
            renderList();
        };
        let appended = false;
        $('report-appendix').addEventListener('toggle', () => {
            if ($('report-appendix').open && !appended) {
                appended = true;
                appendix();
            }
        });
    } catch (error) {
        $('report-status').className = 'error';
        $('report-status').textContent = `보고서를 읽을 수 없습니다: ${error.message}`;
    }
})();
