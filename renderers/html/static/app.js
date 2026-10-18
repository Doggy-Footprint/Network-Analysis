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
    const count = n => n.toLocaleString('ko-KR');
    const definitions = {
        pagerank: ['참조가 모이는 곳', '다른 대상에서 참조받는 상대적 중심성', '상대값'],
        betweenness_centrality: ['경로를 잇는 곳', '대상 사이의 최단 경로를 중개하는 정도', '상대값'],
        hop_2_token_cost: ['주변 코드가 넓은 곳', '연결 두 단계 이내 주변 코드의 할인된 토큰 합', '추정 토큰'],
        weighted_centrality_cost: ['중심에 있는 큰 코드', 'PageRank × 할인된 코드 토큰 수', '가중 토큰'],
        fan_in: ['들어오는 연결이 많은 곳', '이 대상을 참조하는 직접 연결 대상 수', '대상'],
        fan_out: ['나가는 연결이 많은 곳', '이 대상이 참조하는 직접 연결 대상 수', '대상'],
        weighted_fan_in: ['가중 Fan-in', '들어오는 연결 대상별 유효 가중치 합', '가중 연결'],
        weighted_fan_out: ['가중 Fan-out', '나가는 연결 대상별 유효 가중치 합', '가중 연결'],
        token_cost: ['코드 규모', '문자 기반 코드 토큰 추정', '추정 토큰'],
        effective_token_cost: ['할인된 코드 규모', '생성·외부 코드를 할인한 토큰 추정', '추정 토큰']
    };
    const core = Object.keys(definitions).slice(0, 6);
    const kinds = {
        unresolved_boundary: ['정적 분석 미확정 참조', '정적 분석으로 참조·호출 대상을 확정하지 못했거나, 실행 중 해석이 필요한 부분입니다.'],
        evidence_spread: ['근거 분산', '참조 근거가 여러 파일 또는 넓은 줄 범위에 퍼져 있습니다.'],
        large_node: ['큰 노드', '소스 범위가 설정한 줄 수 임계값을 넘습니다.'],
        dependency_cycle: ['의존 순환', '서로 의존해 한 바퀴 돌아오는 파일 묶음입니다. 같은 순환도 연결 확실성 단계별로 따로 표시됩니다.'],
        rule_violation: ['경계 규칙 위반', '아키텍처 규칙 파일에 선언한 layer 경계를 넘는 파일 의존입니다. 허용 목록 밖이거나 금지 규칙에 걸린 경우입니다.']
    };
    const tierLabels = {certain: '확정 연결', resolved: '해석된 연결', all: '불확실 포함'};
    const categoryLabels = {
        all: '전체',
        production: '운영 코드',
        test: '테스트',
        generated: '생성 코드',
        vendored: '외부 코드',
        unknown: '미분류'
    };
    const statusLabels = {complete: '완료', partial: '부분 분석', failed: '실패', skipped: '건너뜀', not_targeted: '대상 밖', excluded: '제외'};

    const glossary = {};
    for (const [name, desc, unit] of Object.values(definitions)) glossary[name] = `${desc} (${unit})`;
    for (const [name, desc] of Object.values(kinds)) glossary[name] = desc;
    Object.assign(glossary, {
        '완료': '선택된 분석 절차가 관측된 오류 없이 끝난 파일입니다. 모든 관계를 발견했다는 보증은 아닙니다.',
        '부분 분석': '분석은 시작했지만 일부 구간이나 분석기가 끝내지 못한 파일입니다.',
        '실패': '분석기가 오류로 결과를 내지 못한 파일입니다.',
        '건너뜀': '분석 대상이었으나 분석을 수행하지 않은 파일입니다.',
        '대상 밖': '분석기가 다루지 않는 종류의 파일입니다.',
        '제외': '수집 정책상 분석 목록에서 제외된 파일입니다.',
        '전체': '모든 코드 분류를 합친 범위입니다.',
        '운영 코드': '테스트·생성·외부 코드가 아닌 저장소 자체 코드입니다.',
        '테스트': '테스트 경로로 분류된 코드입니다.',
        '생성 코드': '코드 생성기가 만든 것으로 분류된 코드입니다.',
        '외부 코드': '저장소에 포함된 외부(vendored) 코드입니다.',
        '미분류': '소스 위치가 없어 분류할 수 없는 대상입니다.',
        '할인': '생성·외부 코드나 불확실한 연결의 기여를 설정 비율만큼 줄여 반영하는 것입니다.',
        '가중': '연결마다 확실도·해석 방식에 따른 가중치(설정값 표)를 곱해 합산한 값입니다.',
        '배분 몫': '모호한 참조를 후보 수로 나눈 몫입니다.',
        '가중 기여도': '가중치 × 배분 몫입니다.',
        'hop': '연결을 따라 이동한 단계 수입니다.',
        'PageRank': '다른 대상에서 참조받는 정도를 연결 구조로 계산한 상대적 중심성입니다.',
        'Betweenness': '대상 사이의 최단 경로가 이 대상을 지나가는 정도입니다.',
        'Fan-in': '이 대상을 참조하는 직접 연결 대상의 수입니다.',
        'Fan-out': '이 대상이 참조하는 직접 연결 대상의 수입니다.',
        'layer': '프레임워크 역할이 있으면 그 역할, 없으면 패키지 경로의 첫 디렉터리로 정한 파일 묶음입니다.'
    });
    window.ReportGlossary = glossary;

    const term = (text, key = text) => {
        const n = el('span', text, 'term');
        if (glossary[key] === undefined) return n;
        n.dataset.term = key;
        n.tabIndex = 0;
        return n;
    };

    const tooltip = $('term-tooltip');
    let tooltipOwner = null;
    function showTooltip(target) {
        const text = glossary[target.dataset.term];
        if (text === undefined) return;
        hideTooltip();
        tooltip.textContent = text;
        tooltip.hidden = false;
        const rect = target.getBoundingClientRect(), box = tooltip.getBoundingClientRect();
        tooltip.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - box.width - 8)) + 'px';
        tooltip.style.top = (rect.bottom + box.height + 12 > window.innerHeight ? Math.max(8, rect.top - box.height - 6) : rect.bottom + 6) + 'px';
        target.setAttribute('aria-describedby', tooltip.id);
        tooltipOwner = target;
    }
    function hideTooltip() {
        tooltipOwner?.removeAttribute('aria-describedby');
        tooltipOwner = null;
        tooltip.hidden = true;
    }
    const termOf = event => event.target instanceof Element ? event.target.closest('[data-term]') : null;
    document.addEventListener('mouseover', event => {
        const target = termOf(event);
        if (target && target !== tooltipOwner) showTooltip(target);
    });
    document.addEventListener('mouseout', event => {
        const target = termOf(event);
        if (target && target === tooltipOwner && !target.contains(event.relatedTarget)) hideTooltip();
    });
    document.addEventListener('focusin', event => {
        const target = termOf(event);
        if (target) showTooltip(target);
    });
    document.addEventListener('focusout', event => {
        if (termOf(event) === tooltipOwner) hideTooltip();
    });
    document.addEventListener('keydown', event => {
        if (event.key === 'Escape') hideTooltip();
    });

    let data, arch, bottlenecks, network, nodes, nodeMap, metrics, candidates, byTarget, incident, category, page = 0,
        fileMode = false, layers = {}, layerColors = new Map(), projected = [];
    let graphEnabled = false, graphDirty = true, activeTab = 'list', graphNodes = [], graphNodeIds = new Set(), nodeData = null;
    let lastFocus = null, modalNode = null;
    const categorySelect = $('category-filter').querySelector('select'),
        sortSelect = $('metric-sort').querySelector('select'),
        kindSelect = $('candidate-kind-filter').querySelector('select'),
        limitSelect = $('list-limit').querySelector('select'),
        sizeSelect = $('graph-size').querySelector('select');

    function isFile(node) {
        return fileMode ? node?.id.startsWith('file:') && !node.metadata?.boundary : true;
    }

    function candidateTargets(edge) {
        return edge.resolution === 'ambiguous' ? [...new Set([edge.to_id, ...(edge.candidates || [])])].sort(cmp) : [edge.to_id];
    }

    function candidateShare(edge) {
        const explicit = edge.metadata?.candidate_share;
        if (explicit !== undefined) {
            if (candidateTargets(edge).length !== 1) throw new Error('candidate_share는 단일 집계 대상에만 사용할 수 있습니다.');
            if (typeof explicit !== 'number' || !Number.isFinite(explicit) || explicit <= 0 || explicit > 1) throw new Error('candidate_share가 올바르지 않습니다.');
            return explicit;
        }
        return 1 / candidateTargets(edge).length;
    }

    function contribution(edge) {
        const weights = bottlenecks?.edge_weights || arch?.stats?.analysis?.edge_weights;
        return Math.min(weights?.confidence?.[edge.confidence || 'static_certain'] ?? 1,
                        weights?.resolution?.[edge.resolution || 'exact'] ?? 1) * (edge.projected_share ?? candidateShare(edge));
    }

    function projectedEdges(edges) {
        return edges.flatMap(edge => (edge.metadata?.candidate_share !== undefined ? [edge.to_id] : candidateTargets(edge)).map(target =>
            ({...edge, to_id: target, projected_share: candidateShare(edge), original: edge})));
    }

    function nodeName(node) {
        const name = node.display_label || node.label || node.id;
        const path = node.span?.file_path;
        return ['file', 'module', 'package'].includes(node.category) && path && name === path ? path.replace(/\\/g, '/').split('/').pop() : name;
    }

    function nodePath(node) {
        return node.span?.file_path || node.metadata?.file_path || (node.id.startsWith('file:') ? node.id.slice(5) : '');
    }

    function button(node) {
        const b = el('button', undefined, 'node-button');
        b.dataset.nodeId = node.id;
        const label = el('span', undefined, 'node-label-block');
        label.append(el('span', nodeName(node), 'node-name'));
        label.append(el('span', node.span?.file_path || '소스 위치 없음', 'path'));
        b.append(label);
        b.addEventListener('click', () => openModal(node.id));
        return b;
    }

    function badges(id, parent) {
        const ks = new Set((byTarget.get(id) || []).map(c => c.kind));
        for (const k of ks) {
            const badge = el('span', undefined, 'badge');
            badge.append(term(kinds[k]?.[0] || k));
            parent.append(badge);
        }
    }

    function eligible() {
        if (arch) return nodes.filter(n => isFile(n) && metrics[n.id] && (category === 'all' || data.categories[n.id] === category));
        if (category === 'all') return nodes.filter(n => isFile(n) && metrics[n.id]);
        const ids = new Set(Object.values(network.rankings_by_category?.[category] || {}).flat().map(r => r.node_id));
        return nodes.filter(n => isFile(n) && ids.has(n.id));
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
            const name = definitions[key][0], card = el('article', undefined, 'metric-card');
            card.dataset.metricGroup = key;
            const heading = el('h3');
            heading.append(term(name));
            card.append(heading);
            const rows = sorted(available.filter(n => finite(metrics[n.id]?.[key])), key);
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
            tr.addEventListener('click', event => {
                if (!event.target.closest('button')) openModal(n.id);
            });
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
        $('list-count').textContent = `${count(rows.length)}개 표시 / 조건 일치 ${count(matchingCount)}개 · 전체 ${count(nodes.filter(n=>isFile(n) && metrics[n.id]).length)}개 대상`;
        $('page-label').textContent = `${rows.length?page+1:0} / ${Math.ceil(rows.length/50)} 페이지`;
        $('page-prev').disabled = page === 0;
        $('page-next').disabled = (page + 1) * 50 >= rows.length;
        const heading = $('sort-heading');
        heading.replaceChildren(term(definitions[key]?.[0] || key));
    }

    function candidateReason(c) {
        const m = c.metrics || {};
        if (c.kind === 'large_node') return `${format(m.line_count)}줄`;
        if (c.kind === 'evidence_spread') return `${format(m.file_count)}개 파일`;
        if (c.kind === 'dependency_cycle') return `${format(m.member_count)}개 파일 순환 · ${tierLabels[c.structure?.tier] || c.structure?.tier}`;
        if (c.kind === 'rule_violation') return `${c.structure?.from_layer} → ${c.structure?.to_layer} · ${c.structure?.rule_type === 'allow' ? '허용 목록 밖' : '금지 규칙'}`;
        return `미확정 참조 ${format(m.unresolved_count)}건`;
    }

    /* ---------- modal ---------- */
    const backdrop = $('modal-backdrop'), dialog = $('node-modal'), closeButton = $('modal-close');

    function neighbors(id) {
        const result = {incoming: new Map(), outgoing: new Map()};
        for (const e of incident.get(id) || []) {
            if (e.from_id === e.to_id) continue;
            const side = e.from_id === id ? result.outgoing : result.incoming, other = e.from_id === id ? e.to_id : e.from_id;
            side.set(other, (side.get(other) || 0) + contribution(e));
        }
        return result;
    }

    function connectionColumn(title, direction, map) {
        const column = el('div', undefined, 'connections');
        column.dataset.direction = direction;
        column.append(el('h3', `${title} · 총 ${count(map.size)}개`));
        const list = el('div', undefined, 'connection-list');
        for (const [other, weight] of [...map].sort((a, b) => b[1] - a[1] || cmp(a[0], b[0])).slice(0, 10)) {
            const target = nodeMap.get(other) || {id: other};
            const row = el('div', undefined, 'connection');
            row.dataset.connectionId = other;
            row.append(button(target), el('span', format(weight), 'value'));
            list.append(row);
        }
        if (!map.size) list.append(el('div', '연결 없음', 'empty'));
        column.append(list);
        return column;
    }

    function renderModal(id) {
        const n = nodeMap.get(id), host = $('modal-content');
        host.replaceChildren();
        const head = el('div', undefined, 'modal-head');
        const title = el('h2', nodeName(n));
        title.id = 'modal-title';
        head.append(title, el('div', nodePath(n) || '소스 위치 없음', 'path'));
        const tags = el('div', undefined, 'modal-tags');
        const layer = layers[id];
        if (layer) {
            const badge = el('span', layer.layer, 'badge layer-badge');
            badge.dataset.layer = layer.layer;
            tags.append(badge);
        }
        if (data.categories?.[id]) {
            const badge = el('span', undefined, 'badge');
            badge.append(term(categoryLabels[data.categories[id]] || data.categories[id]));
            tags.append(badge);
        }
        if (tags.childNodes.length) head.append(tags);
        host.append(head);
        const values = el('div', undefined, 'metrics');
        for (const key of core) {
            const box = el('div', undefined, 'metric-value');
            box.dataset.metric = key;
            const label = el('span');
            label.append(term(definitions[key][0]));
            box.append(label, el('strong', format(metrics[id]?.[key])));
            values.append(box);
        }
        for (const [label, value] of [['줄 수', n.cost?.line_count], ['토큰 수', n.cost?.token_estimate ?? metrics[id]?.token_cost]]) {
            const box = el('div', undefined, 'metric-value');
            box.append(el('span', label), el('strong', format(value)));
            values.append(box);
        }
        host.append(values);
        const candidateBox = el('div', undefined, 'modal-candidates');
        const list = byTarget.get(id) || [];
        if (!list.length) candidateBox.append(el('div', '후보 없음', 'empty'));
        for (const c of list) {
            const line = el('div', undefined, 'candidate-line');
            line.dataset.candidateKind = c.kind;
            line.append(term(kinds[c.kind]?.[0] || c.kind), document.createTextNode(' · ' + candidateReason(c)));
            candidateBox.append(line);
        }
        host.append(candidateBox);
        const links = neighbors(id), grid = el('div', undefined, 'connection-grid');
        grid.append(connectionColumn('들어오는 연결', 'incoming', links.incoming), connectionColumn('나가는 연결', 'outgoing', links.outgoing));
        host.append(grid);
    }

    function openModal(id) {
        if (!nodeMap.has(id)) return;
        if (backdrop.hidden) lastFocus = document.activeElement;
        hideTooltip();
        modalNode = id;
        renderModal(id);
        backdrop.hidden = false;
        closeButton.focus({preventScroll: true});
        if (activeTab === 'graph' && window.ReportGraph && graphNodeIds.has(id)) {
            window.ReportGraph.selectNodes([id]);
            window.ReportGraph.focus(id, {scale: window.ReportGraph.getScale(), animation: {duration: 250, easingFunction: 'easeInOutQuad'}});
        }
    }

    function closeModal() {
        if (backdrop.hidden) return;
        hideTooltip();
        backdrop.hidden = true;
        modalNode = null;
        const target = lastFocus;
        lastFocus = null;
        if (target && document.contains(target)) target.focus({preventScroll: true});
    }

    closeButton.addEventListener('click', closeModal);
    backdrop.addEventListener('click', event => {
        if (event.target === backdrop) closeModal();
    });
    document.addEventListener('keydown', event => {
        if (backdrop.hidden) return;
        if (event.key === 'Escape') {
            event.preventDefault();
            closeModal();
        } else if (event.key === 'Tab') {
            const focusable = [...dialog.querySelectorAll('button:not([disabled]), [tabindex="0"], input, select, a[href]')].filter(n => n.getClientRects().length);
            if (!focusable.length) return;
            const first = focusable[0], last = focusable[focusable.length - 1];
            if (!dialog.contains(document.activeElement)) {
                event.preventDefault();
                first.focus({preventScroll: true});
            } else if (event.shiftKey && document.activeElement === first) {
                event.preventDefault();
                last.focus({preventScroll: true});
            } else if (!event.shiftKey && document.activeElement === last) {
                event.preventDefault();
                first.focus({preventScroll: true});
            }
        }
    });
    document.addEventListener('focusin', event => {
        if (!backdrop.hidden && !dialog.contains(event.target) && !tooltip.contains(event.target)) closeButton.focus({preventScroll: true});
    });

    /* ---------- graph ---------- */
    function layerColor(index) {
        const hue = (index * 137.508) % 360, s = 0.55, l = 0.55;
        const a = s * Math.min(l, 1 - l);
        const channel = n => {
            const k = (n + hue / 30) % 12;
            return Math.round(255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1)))).toString(16).padStart(2, '0');
        };
        return '#' + channel(0) + channel(8) + channel(4);
    }

    function nodeSizes(rows, key) {
        const raw = rows.map(n => {
            const v = metrics[n.id]?.[key];
            return finite(v) ? Math.sqrt(Math.max(0, v)) : null;
        });
        const present = raw.filter(v => v !== null);
        const lo = Math.min(...present), hi = Math.max(...present);
        return raw.map(v => v === null || !(hi > lo) ? 10 : 10 + 40 * (v - lo) / (hi - lo));
    }

    function setGraphStatus(text) {
        $('graph-status').textContent = text;
    }

    function renderLegend(rows) {
        const host = $('graph-legend');
        host.replaceChildren();
        const tally = new Map();
        for (const n of rows) {
            const name = layers[n.id]?.layer || '(root)';
            tally.set(name, (tally.get(name) || 0) + 1);
        }
        const head = el('span', undefined, 'legend-group');
        head.append(term('layer'), document.createTextNode(' '));
        host.append(head);
        for (const [name, total] of [...tally].sort((a, b) => b[1] - a[1] || cmp(a[0], b[0]))) {
            const item = el('span', undefined, 'legend-item');
            item.dataset.layer = name;
            const swatch = el('i', undefined, 'swatch');
            swatch.style.background = layerColor(layerColors.get(name) ?? 0);
            item.append(swatch, el('span', name), el('b', String(total)));
            host.append(item);
        }
        const mark = el('span', undefined, 'legend-item legend-candidate');
        mark.append(el('i', undefined, 'swatch candidate-swatch'), el('span', '후보'));
        host.append(mark);
        const meta = el('span', undefined, 'legend-group');
        meta.append(document.createTextNode('코드 분류 '), term(categoryLabels[category] || category), document.createTextNode(' · 크기 '), term(definitions[sizeSelect.value][0]));
        host.append(meta);
    }

    function destroyGraph() {
        if (window.ReportGraph) {
            window.ReportGraph.destroy();
            window.ReportGraph = null;
        }
        nodeData = null;
        document.body.dataset.graphReady = 'false';
    }

    function buildGraph() {
        destroyGraph();
        graphDirty = false;
        graphNodes = nodes.filter(n => n.kind === 'file' && isFile(n) && (category === 'all' || data.categories[n.id] === category));
        graphNodeIds = new Set(graphNodes.map(n => n.id));
        renderLegend(graphNodes);
        const options = $('graph-search-options');
        options.replaceChildren(...graphNodes.map(n => {
            const option = document.createElement('option');
            option.value = nodePath(n);
            return option;
        }));
        setGraphStatus('');
        const sizes = nodeSizes(graphNodes, sizeSelect.value);
        const visNodes = graphNodes.map((n, i) => {
            const color = layerColor(layerColors.get(layers[n.id]?.layer || '(root)') ?? 0), flagged = byTarget.has(n.id);
            const border = flagged ? '#d9480f' : '#5b6b72';
            return {
                id: n.id,
                label: nodeName(n),
                title: `${nodePath(n)}\n${layers[n.id]?.layer || '(root)'}`,
                size: sizes[i],
                borderWidth: flagged ? 3 : 1,
                color: {background: color, border, highlight: {background: color, border}, hover: {background: color, border}}
            };
        });
        const pairs = new Map();
        for (const e of projected) {
            if (e.from_id === e.to_id || !graphNodeIds.has(e.from_id) || !graphNodeIds.has(e.to_id)) continue;
            const key = e.from_id + '\u0000' + e.to_id;
            let entry = pairs.get(key);
            if (!entry) pairs.set(key, entry = {from: e.from_id, to: e.to_id, relations: new Map()});
            entry.relations.set(e.relation, (entry.relations.get(e.relation) || 0) + 1);
        }
        const visEdges = [...pairs.values()].map(p => ({
            from: p.from,
            to: p.to,
            title: [...p.relations].sort((a, b) => b[1] - a[1] || cmp(a[0], b[0])).map(([name, total]) => `${name} ${total}`).join(' · ')
        }));
        if (!visNodes.length) {
            setGraphStatus('표시할 파일이 없습니다.');
            document.body.dataset.graphReady = 'true';
            return;
        }
        nodeData = new vis.DataSet(visNodes);
        const finish = () => {
            if (!window.ReportGraph) return;
            window.ReportGraph.setOptions({physics: false});
            window.ReportGraph.fit();
            document.body.dataset.graphReady = 'true';
        };
        try {
            window.ReportGraph = new vis.Network($('graph-container'), {nodes: nodeData, edges: new vis.DataSet(visEdges)}, {
                physics: {
                    solver: 'barnesHut',
                    barnesHut: {gravitationalConstant: -12000, centralGravity: 0.8, springLength: 180, springConstant: 0.02, damping: 0.5, avoidOverlap: 0.5},
                    stabilization: {enabled: true, iterations: 250, updateInterval: 50, fit: true}
                },
                nodes: {shape: 'dot', font: {size: 12, strokeWidth: 3, strokeColor: '#ffffff'}},
                edges: {arrows: {to: {enabled: true, scaleFactor: 0.4}}, color: {color: '#b4c2c6', highlight: '#126d64', hover: '#126d64'}, width: 1, smooth: false, selectionWidth: 2},
                interaction: {hover: true, tooltipDelay: 120, hideEdgesOnDrag: true, zoomView: true},
                layout: {improvedLayout: false}
            });
            window.ReportGraph.once('stabilizationIterationsDone', finish);
            window.ReportGraph.on('click', params => {
                if (params.nodes.length) openModal(params.nodes[0]);
            });
        } catch (error) {
            window.ReportGraph = null;
            disableGraph('그래프를 초기화할 수 없습니다. 목록을 사용하세요.');
        }
    }

    function disableGraph(reason) {
        destroyGraph();
        delete document.body.dataset.graphReady;
        graphEnabled = false;
        $('tab-graph').disabled = true;
        $('graph-search').closest('.graph-toolbar').hidden = true;
        $('graph-legend').hidden = true;
        $('panel-graph').hidden = false;
        $('graph-container').className = 'graph-unavailable';
        $('graph-container').textContent = reason;
        setTab('list');
    }

    function setTab(name) {
        if (name === 'graph' && !graphEnabled) return;
        activeTab = name;
        $('tab-graph').setAttribute('aria-selected', String(name === 'graph'));
        $('tab-list').setAttribute('aria-selected', String(name === 'list'));
        if (graphEnabled) $('panel-graph').hidden = name !== 'graph';
        $('panel-list').hidden = name !== 'list';
        if (name === 'graph' && graphEnabled) {
            if (graphDirty) buildGraph();
            else window.ReportGraph?.redraw();
        }
    }

    function refreshGraph() {
        if (!graphEnabled) return;
        graphDirty = true;
        if (activeTab === 'graph') buildGraph();
        else destroyGraph();
    }

    function setupGraph() {
        let reason = null;
        if (!arch) reason = '아키텍처 데이터가 없어 그래프를 그릴 수 없습니다.';
        else if (arch.granularity !== 'file') reason = '파일 단위 보고서에서만 그래프를 제공합니다.';
        else if (window.__visFailed || typeof window.vis?.Network !== 'function' || typeof window.vis?.DataSet !== 'function') reason = '그래프 라이브러리를 불러오지 못했습니다. 목록을 사용하세요.';
        if (reason) {
            disableGraph(reason);
            return;
        }
        graphEnabled = true;
        const tally = new Map();
        for (const n of nodes) if (n.kind === 'file' && isFile(n)) {
            const name = layers[n.id]?.layer || '(root)';
            tally.set(name, (tally.get(name) || 0) + 1);
        }
        [...tally].sort((a, b) => b[1] - a[1] || cmp(a[0], b[0])).forEach(([name], index) => layerColors.set(name, index));
        for (const key of [...core, 'token_cost']) {
            const option = el('option', definitions[key][0]);
            option.value = key;
            sizeSelect.append(option);
        }
        sizeSelect.value = 'pagerank';
        sizeSelect.onchange = () => {
            if (!window.ReportGraph || !nodeData) {
                graphDirty = true;
                return;
            }
            const sizes = nodeSizes(graphNodes, sizeSelect.value);
            nodeData.update(graphNodes.map((n, i) => ({id: n.id, size: sizes[i]})));
            renderLegend(graphNodes);
        };
        $('graph-reset').onclick = () => {
            if (!window.ReportGraph) return;
            window.ReportGraph.unselectAll();
            window.ReportGraph.fit();
            setGraphStatus('');
        };
        $('graph-search').oninput = () => {
            const query = $('graph-search').value.trim().toLocaleLowerCase();
            if (!query || !window.ReportGraph) {
                setGraphStatus('');
                return;
            }
            const hits = graphNodes.filter(n => nodePath(n).toLocaleLowerCase().includes(query));
            const hit = hits.find(n => nodePath(n).toLocaleLowerCase() === query) || hits.sort((a, b) => cmp(nodePath(a), nodePath(b)))[0];
            if (!hit) {
                setGraphStatus('일치하는 파일 없음');
                return;
            }
            setGraphStatus(`${count(hits.length)}개 일치`);
            window.ReportGraph.selectNodes([hit.id]);
            window.ReportGraph.focus(hit.id, {scale: 1.2, animation: false});
        };
    }

    /* ---------- page sections ---------- */
    function pill(key, label) {
        const box = el('div', undefined, 'pill');
        box.dataset.kpi = key;
        box.append(typeof label === 'string' ? el('span', label, 'pill-label') : label);
        return box;
    }

    function renderKpi() {
        const host = $('kpi');
        const fileNodes = arch ? nodes.filter(n => isFile(n) && (n.kind === 'file' || !fileMode)) : null;
        const files = arch ? (fileMode ? fileNodes.length : new Set(nodes.map(n => n.span?.file_path).filter(Boolean)).size) : bottlenecks?.snapshot?.file_count;
        const filesPill = pill('files', '파일');
        filesPill.append(el('strong', finite(files) ? count(files) : '—'));
        const edges = network.edge_count ?? arch?.edges?.length;
        const edgesPill = pill('edges', '연결');
        edgesPill.append(el('strong', finite(edges) ? count(edges) : '—'));
        const candidatePill = pill('candidates', '후보');
        candidatePill.append(el('strong', bottlenecks ? count(candidates.length) : '—'));
        const kindList = el('span', undefined, 'pill-detail');
        for (const [key, [label]] of Object.entries(kinds)) {
            const item = el('span', undefined, 'pill-item');
            item.dataset.candidateKind = key;
            item.append(term(label), document.createTextNode(' '), el('b', bottlenecks ? String(candidates.filter(c => c.kind === key).length) : '—'));
            kindList.append(item);
        }
        candidatePill.append(kindList);
        const coverage = arch?.stats?.analysis_coverage || bottlenecks?.coverage?.analysis_coverage;
        const coveragePill = pill('coverage', '분석 범위');
        if (!coverage) coveragePill.append(el('strong', '분석 범위 정보 없음', 'pill-text'));
        else {
            const detail = el('span', undefined, 'pill-detail');
            for (const status of ['complete', 'partial', 'failed']) {
                const item = el('span', undefined, 'pill-item');
                item.dataset.coverageStatus = status;
                item.append(term(statusLabels[status]), document.createTextNode(' '), el('b', String(coverage.summary?.[status + '_file_count'] ?? '—')));
                detail.append(item);
            }
            coveragePill.append(detail);
        }
        host.append(filesPill, edgesPill, candidatePill, coveragePill);
        $('scope').textContent = `${arch?.project_path||'JSON 병목 보고서'} · ${data.framework_label||'정적 분석'}`;
    }

    function appendix() {
        const weights = bottlenecks?.edge_weights || arch?.stats?.analysis?.edge_weights;
        const body = $('settings-table').querySelector('tbody');
        const addRow = (group, item, value) => {
            const tr = el('tr');
            const first = el('td');
            first.append(group);
            tr.append(first, el('td', item), el('td', format(value)));
            body.append(tr);
        };
        if (!weights) {
            const tr = el('tr'), td = el('td', '설정값 정보 없음');
            td.colSpan = 3;
            tr.append(td);
            body.append(tr);
        }
        else {
            for (const [name, label] of [['confidence', '확실도'], ['resolution', '해석 방식']])
                for (const [item, value] of Object.entries(weights[name] || {})) {
                    const group = document.createDocumentFragment();
                    group.append(label + ' ', term('가중'));
                    addRow(group, item, value);
                }
            if (weights.large_node_line_threshold !== undefined) addRow(term('큰 노드'), '줄 수 임계값', weights.large_node_line_threshold);
        }
        const guide = $('reading-guide');
        const item = (...parts) => {
            const li = el('li');
            li.append(...parts.map(p => typeof p === 'string' ? document.createTextNode(p) : p));
            guide.append(li);
        };
        item(term('PageRank'), ' · ', term('Betweenness'), ' · ', term('Fan-in'), ' · ', term('Fan-out'), ': 연결 구조에서의 위치를 보여줍니다.');
        item(term('할인'), ' · ', term('가중'), ': 설정값 표의 비율이 합산에 적용됩니다.');
        item(term('배분 몫'), ' · ', term('가중 기여도'), ' · ', term('hop'), ': 모호한 참조와 주변 범위를 읽을 때 쓰입니다.');
        item(term('layer'), ': 그래프 노드 색의 기준입니다.');
        item('지표는 합산하지 않으며, 후보는 구조적 사실일 뿐 품질·변경 위험·작업 난이도의 판정이 아닙니다.');
    }

    function setupTabs() {
        $('tab-graph').onclick = () => setTab('graph');
        $('tab-list').onclick = () => setTab('list');
        for (const tab of [$('tab-graph'), $('tab-list')]) tab.onkeydown = event => {
            if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
            const next = tab === $('tab-graph') ? 'list' : 'graph';
            if (next === 'graph' && !graphEnabled) return;
            setTab(next);
            $('tab-' + next).focus({preventScroll: true});
        };
    }

    try {
        data = JSON.parse($('report-data').textContent);
        arch = data.architecture;
        bottlenecks = data.bottlenecks;
        if ((arch && arch.stats?.analysis?.ambiguity_policy !== 'equal-symbol-share.v1') || (bottlenecks && bottlenecks.dependency_network?.ambiguity_policy !== 'equal-symbol-share.v1')) throw new Error('지원하지 않거나 누락된 ambiguity_policy입니다.');
        if ((!arch && !bottlenecks) || (arch && (!Array.isArray(arch.nodes) || !Array.isArray(arch.edges))) || (bottlenecks && (!bottlenecks.dependency_network || !Array.isArray(bottlenecks.candidates)))) throw new Error('보고서 데이터 구조가 올바르지 않습니다.');
        for (const graph of [arch, arch?.details].filter(Boolean)) {
            const ids = new Set((graph.nodes || []).map(node => node.id));
            for (const edge of graph.edges || []) {
                if (!ids.has(edge.from_id) || [edge.to_id, ...(edge.candidates || [])].some(target => !ids.has(target))) throw new Error('아키텍처 밖의 후보 참조입니다.');
                candidateShare(edge);
            }
        }
        const candidateGroups = bottlenecks?.dependency_network?.candidate_groups === undefined ? {} : bottlenecks.dependency_network.candidate_groups;
        if (!candidateGroups || typeof candidateGroups !== 'object' || Array.isArray(candidateGroups)) throw new Error('모호한 후보 그룹 데이터가 올바르지 않습니다.');
        for (const [groupId, group] of Object.entries(candidateGroups)) {
            if (!groupId || !group || typeof group !== 'object' || Array.isArray(group) || typeof group.to_id !== 'string' || !group.to_id || !Array.isArray(group.candidates) || group.candidates.some(id => typeof id !== 'string' || !id)) throw new Error('모호한 후보 그룹 데이터가 올바르지 않습니다.');
        }
        for (const candidate of bottlenecks?.candidates || []) {
            const evidence = Array.isArray(candidate.evidence) ? candidate.evidence : [candidate.evidence];
            for (const record of evidence) {
                if (!record || !Object.hasOwn(record, 'candidate_group_id')) continue;
                const groupId = record.candidate_group_id;
                if (typeof groupId !== 'string' || !groupId || !Object.hasOwn(candidateGroups, groupId) || candidateGroups[groupId].to_id !== record.to_id) throw new Error('모호한 후보 그룹 참조가 올바르지 않습니다.');
            }
        }
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
        fileMode = arch?.granularity === 'file' || bottlenecks?.granularity === 'file';
        layers = data.layers || {};
        if (fileMode) {
            kinds.large_node[1] = '파일 전체 줄 수가 설정한 임계값을 넘습니다.';
            $('node-search').placeholder = '파일 이름 또는 경로';
        }
        nodeMap = new Map(nodes.map(n => [n.id, n]));
        candidates = (bottlenecks?.candidates || []).filter(c => !fileMode || c.target.startsWith('file:') || c.kind === 'dependency_cycle');
        byTarget = new Map();
        for (const c of candidates) {
            for (const target of c.kind === 'dependency_cycle' ? (Array.isArray(c.structure?.members) ? c.structure.members : []) : [c.target]) {
                if (!byTarget.has(target)) byTarget.set(target, []);
                byTarget.get(target).push(c);
            }
        }
        projected = projectedEdges(arch?.edges || []);
        incident = new Map();
        for (const e of projected) {
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
        renderKpi();
        renderRepresentatives();
        renderList();
        appendix();
        setupTabs();
        setupGraph();
        if (graphEnabled) setTab('graph');
        categorySelect.onchange = () => {
            category = categorySelect.value;
            page = 0;
            renderRepresentatives();
            renderList();
            refreshGraph();
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
    } catch (error) {
        $('report-status').className = 'error';
        $('report-status').textContent = `보고서를 읽을 수 없습니다: ${error.message}`;
    }
})();
