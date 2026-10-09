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
        selected, relations = [], graphRelations = [], fileMode = false, details = {}, detailMap, detailIncident, fileIncident, implementationEdges, implementationTargets;
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
                const resolved = typeof value === 'function' ? value() : value;
                d.append(el('pre', typeof resolved === 'string' ? resolved : JSON.stringify(resolved, null, 2)));
                built = true;
            }
        });
        parent.append(d);
        return d;
    }

    function isFile(node) {
        return fileMode ? node?.id.startsWith('file:') && !node.metadata?.boundary : true;
    }

    function symbolKind(node) {
        return node?.kind || node?.category;
    }

    function visibleSymbol(node) {
        const kind = symbolKind(node);
        return ['class', 'interface', 'function'].includes(kind) ||
            (!['method', 'field', 'constant', 'type_alias', 'enum', 'configuration', 'config', 'file', 'module', 'package'].includes(kind) &&
                ['android', 'fastapi', 'sqlalchemy', 'nestjs'].includes(node?.provenance));
    }

    function displayOwner(id) {
        const seen = new Set();
        let current = implementationTargets.get(id) || id;
        const initial = detailMap.get(current);
        if (!visibleSymbol(initial) && !['method', 'field'].includes(symbolKind(initial))) return details.node_files?.[current] || current;
        while (current && !seen.has(current)) {
            seen.add(current);
            const node = detailMap.get(current);
            if (visibleSymbol(node) && (!['method', 'field'].includes(symbolKind(initial)) || ['class', 'interface'].includes(symbolKind(node)))) return current;
            current = details.node_owners?.[current];
        }
        return details.node_files?.[id] || id;
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

    function declarationEdge(edge) {
        if (edge.relation === 'IMPLEMENTED_BY') return true;
        if (!['CONTAINS', 'DECLARES', 'EXPORTS'].includes(edge.relation)) return false;
        const from = detailMap.get(edge.from_id), to = detailMap.get(edge.to_id);
        const language = ['python-core', 'typescript-core', 'kotlin-core'];
        const declarations = ['package', 'module', 'file', 'class', 'interface', 'enum', 'function', 'method', 'field', 'constant', 'type_alias'];
        return language.includes(from?.provenance) && language.includes(to?.provenance) &&
            declarations.includes(symbolKind(from)) && declarations.includes(symbolKind(to));
    }

    function symbolGraphRelations(id) {
        const file = details.node_files?.[id];
        const result = [];
        for (const original of detailIncident.get(id) || []) {
            const endpoint = key => {
                const target = implementationTargets.get(key) || key;
                const targetFile = details.node_files?.[target];
                return targetFile && targetFile !== file ? targetFile : displayOwner(target);
            };
            const pairs = new Map();
            for (const edge of projectedEdges([original])) {
                const source = endpoint(edge.from_id), target = endpoint(edge.to_id);
                if (source === target || (source !== id && target !== id)) continue;
                const key = JSON.stringify([source, target]);
                if (pairs.has(key)) pairs.get(key).projected_share += edge.projected_share;
                else pairs.set(key, {...edge, from_id: source, to_id: target, original});
            }
            result.push(...pairs.values());
        }
        return result;
    }

    function fileSymbols(id, host) {
        const ids = details.file_nodes?.[id] || [];
        const source = ids.map(key => detailMap.get(key)).filter(Boolean);
        const roles = new Map();
        const implemented = new Set();
        for (const edge of implementationEdges.get(id) || []) {
            if (!roles.has(edge.to_id)) roles.set(edge.to_id, []);
            roles.get(edge.to_id).push(detailMap.get(edge.from_id));
            implemented.add(edge.from_id);
        }
        const visible = source.filter(node => !implemented.has(node.id) && visibleSymbol(node));
        const visibleIds = new Set(visible.map(node => node.id));
        const children = new Map();
        for (const node of visible) {
            let parent = details.node_owners?.[node.id];
            const seen = new Set([node.id]);
            while (parent && !visibleIds.has(parent) && !seen.has(parent)) {
                seen.add(parent);
                parent = details.node_owners?.[parent];
            }
            if (!visibleIds.has(parent)) parent = null;
            if (!children.has(parent)) children.set(parent, []);
            children.get(parent).push(node);
        }
        const foldedByOwner = new Map();
        for (const member of source) {
            if (!['method', 'field'].includes(member.kind || member.category)) continue;
            const owner = displayOwner(member.id);
            if (!foldedByOwner.has(owner)) foldedByOwner.set(owner, []);
            foldedByOwner.get(owner).push(member);
        }
        host.append(el('h3', '클래스 · 인터페이스 · 함수'));
        const tree = el('div', undefined, 'symbol-list');
        tree.id = 'file-symbols';
        const draw = (parent, into, seen) => {
            for (const node of children.get(parent) || []) {
                if (seen.has(node.id)) continue;
                const row = el('div', undefined, 'symbol-entry');
                row.dataset.symbolId = node.id;
                row.append(button(node), el('span', node.kind || node.category || '프레임워크', 'badge'));
                for (const role of roles.get(node.id) || []) if (role) row.append(el('span', role.category || role.kind || role.label, 'badge framework-role'));
                const folded = foldedByOwner.get(node.id) || [];
                if (folded.length) {
                    const members = el('details');
                    members.append(el('summary', `메서드 · 필드 ${folded.length}개`));
                    let built = false;
                    members.addEventListener('toggle', () => {
                        if (!members.open || built) return;
                        built = true;
                        for (const member of folded) {
                            const item = el('div', undefined, 'folded-symbol');
                            item.dataset.foldedSymbolId = member.id;
                            item.append(button(member), el('span', member.kind || member.category, 'badge'));
                            for (const role of roles.get(member.id) || []) if (role) item.append(el('span', role.category || role.kind || role.label, 'badge framework-role'));
                            rawDetails('선언의 전체 기록', member, item);
                            members.append(item);
                        }
                    });
                    row.append(members);
                }
                const nested = el('div', undefined, 'symbol-children');
                draw(node.id, nested, new Set([...seen, node.id]));
                if (nested.childNodes.length) row.append(nested);
                into.append(row);
            }
        };
        draw(null, tree, new Set());
        if (!visible.length) tree.append(el('p', '표시할 선언이 없습니다. 제공된 참조는 파일 본문과 전체 연결 목록에서 확인하세요.', 'muted'));
        host.append(tree);
        const body = source.filter(node => !visibleIds.has(node.id) && !implemented.has(node.id));
        if (body.length) rawDetails('파일 본문 · 접힌 선언과 참조', body, host);
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
        $('list-count').textContent = `${rows.length.toLocaleString('ko-KR')}개 표시 / 조건 일치 ${matchingCount.toLocaleString('ko-KR')}개 · 전체 ${nodes.filter(n=>isFile(n) && metrics[n.id]).length.toLocaleString('ko-KR')}개 대상`;
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
            for (const id of [edge.from_id, ...candidateTargets(edge.original || edge)]) {
                const currentFile = details.node_files?.[selected] || (isFile(nodeMap.get(selected)) ? selected : null);
                const targetFile = details.node_files?.[id];
                const destination = fileMode && targetFile && currentFile && targetFile !== currentFile ? targetFile : fileMode ? displayOwner(id) : id;
                const n = nodeMap.get(destination) || detailMap.get(destination) || {id: destination};
                row.append(button(n));
                if (id === edge.from_id) row.append(el('span', ' → '));
            }
            row.append(el('div', `${edge.relation||'관계'} · ${edge.confidence||'static_certain'} · ${edge.resolution||'exact'} · 중복 횟수 ${format(edge.weight ?? 1)}`));
            row.append(el('div', `배분 몫 ${format(edge.projected_share ?? candidateShare(edge))} · 가중 기여도 ${format(contribution(edge))}`));
            const original = edge.original || edge;
            if (original.resolution === 'ambiguous') {
                for (const target of candidateTargets(original)) {
                    const projected = {...original, to_id: target, projected_share: candidateShare(original)};
                    const name = (detailMap.get(target) || nodeMap.get(target))?.display_label || (detailMap.get(target) || nodeMap.get(target))?.label || target;
                    row.append(el('div', `${name} · 배분 몫 ${format(candidateShare(original))} · 가중 기여도 ${format(contribution(projected))}`));
                }
                if (fileMode) {
                    const shares = new Map();
                    const source = details.node_files?.[original.from_id] || original.from_id;
                    for (const target of candidateTargets(original)) {
                        const file = details.node_files?.[target] || target;
                        if (file !== source) shares.set(file, (shares.get(file) || 0) + candidateShare(original));
                    }
                    for (const [file, share] of shares) row.append(el('div', `${(nodeMap.get(file)?.label || file)} · 파일 배분 몫 ${format(share)} · 가중 기여도 ${format(contribution({...original, projected_share: share}))}`));
                }
            }
            if (edge.resolution === 'ambiguous') row.append(el('div', '모호한 후보 그룹: 가능한 대안'));
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
        const neighbors = new Map();
        for (const e of graphRelations) {
            const other = e.from_id === id ? e.to_id : e.from_id;
            if (other === id || !(nodeMap.has(other) || detailMap.has(other))) continue;
            const weight = contribution(e);
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
        const chosen = [...neighbors].sort((a, b) => b[1].weight - a[1].weight || (finite(metrics[details.node_files?.[b[0]] || b[0]]?.fan_in) ? metrics[details.node_files?.[b[0]] || b[0]].fan_in : 0) - (finite(metrics[details.node_files?.[a[0]] || a[0]]?.fan_in) ? metrics[details.node_files?.[a[0]] || a[0]].fan_in : 0) || cmp(a[0], b[0])).slice(0, 30);
        status.dataset.shown = String(chosen.length);
        status.dataset.omitted = String(neighbors.size - chosen.length);
        status.textContent = `직접 이웃 ${chosen.length}개 표시 · ${neighbors.size-chosen.length}개 생략 · 분류 필터와 관계없이 연결 표시`;
        const elements = [{
                data: {
                    id,
                    label: (detailMap.get(id) || nodeMap.get(id)).display_label || (detailMap.get(id) || nodeMap.get(id)).label || id,
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
                    label: (detailMap.get(key) || nodeMap.get(key)).display_label || (detailMap.get(key) || nodeMap.get(key)).label || key
                },
                position
            });
        }
        $('graph-container').style.height = compact && chosen.length > 15 ? '520px' : '';
        for (const e of graphRelations) {
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
                for (const e of event.target.data('relations')) { host.append(el('div', `${e.resolution || 'exact'} · 배분 몫 ${format(e.projected_share ?? candidateShare(e))} · 가중 기여도 ${format(contribution(e))} · 중복 횟수 ${format(e.weight ?? 1)}`)); host.append(el('pre', JSON.stringify(e.original || e, null, 2))); }
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

    function resolvedCandidate(c) {
        const resolve = record => {
            if (!record || !record.candidate_group_id) return record;
            const group = network.candidate_groups?.[record.candidate_group_id];
            return {...record, to_id: group.to_id, candidates: group.candidates};
        };
        return {...c, evidence: Array.isArray(c.evidence) ? c.evidence.map(resolve) : resolve(c.evidence)};
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
        if (fileMode && detailMap.has(id)) id = displayOwner(id);
        const original = detailMap.get(id);
        const n = nodeMap.get(id) || original;
        if (!n) return;
        const symbol = fileMode && !!original && !!details.node_files?.[id];
        const ownerFile = symbol ? details.node_files?.[id] : isFile(n) ? id : null;
        selected = id;
        relationshipPage = 0;
        relations = symbol ? detailIncident.get(id) || [] : fileMode && isFile(n) ? fileIncident.get(id) || [] : fileMode ? detailIncident.get(id) || incident.get(id) || [] : incident.get(id) || [];
        relations = [...new Set(relations.map(edge => edge.original || edge))];
        graphRelations = symbol ? symbolGraphRelations(id) : incident.get(id) || [];
        const host = $('node-detail');
        host.replaceChildren();
        host.dataset.selectedNode = id;
        host.dataset.selectedFile = ownerFile || '';
        host.dataset.detailKind = symbol ? 'symbol' : fileMode && !isFile(n) ? 'boundary' : 'file';
        if (symbol && ownerFile) {
            const back = el('button', '파일 상세로 돌아가기');
            back.id = 'back-to-file';
            back.onclick = () => selectNode(ownerFile);
            host.append(back);
        }
        host.append(el('div', '03 / 대상 상세', 'eyebrow'), el('h2', n.display_label || n.label || id), el('p', n.span ? evidenceText(n.span) : '소스 위치 정보 없음', 'path'));
        const values = el('div', undefined, 'metrics');
        for (const key of symbol ? [] : Object.keys(definitions)) {
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
            rawDetails('후보의 전체 기록', () => resolvedCandidate(c), box);
            host.append(box);
        }
        if (!symbol) rawDetails(fileMode ? '파일 전체 지표' : '전체 지표 · 식별자 출현 컨텍스트', metrics[id] || {}, host);
        if (symbol && n.docstring) host.append(el('p', n.docstring));
        if (fileMode && isFile(n)) fileSymbols(id, host);
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
        host.append(el('p', fileMode ? '파일 토큰은 파일 전체 텍스트에서 한 번 계산합니다. 파일 간 경로는 함수 호출 연쇄를 보장하지 않습니다.' : '토큰은 문자 기반 추정치입니다. 소스 범위가 겹칠 수 있으므로 합계를 저장소 고유 텍스트 양이나 실제 LLM 사용량으로 해석하면 안 됩니다. 식별자 컨텍스트별 파일 수는 서로 겹칠 수 있습니다.'));
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
    function renderCoverage() {
        const coverage = arch?.stats?.analysis_coverage || bottlenecks?.coverage?.analysis_coverage;
        const summary = $('coverage-summary'), disclosure = $('coverage-details');
        if (!coverage) {
            summary.append(el('p', '분석 범위 정보 없음: 스냅샷 없는 분석 또는 이전 보고서입니다.', 'notice'));
            disclosure.hidden = true;
            return;
        }
        const labels = {complete: '완료', partial: '부분 분석', failed: '실패', skipped: '건너뜀', not_targeted: '대상 밖', excluded: '제외'};
        const producers = {'python-core': 'Python', 'typescript-core': 'TypeScript·JavaScript', 'kotlin-core': 'Kotlin', fastapi: 'FastAPI', android: 'Android', sqlalchemy: 'SQLAlchemy', nestjs: 'NestJS'};
        const counts = el('div', undefined, 'counts');
        for (const [status, label] of Object.entries(labels)) {
            const box = el('div', undefined, 'count');
            box.dataset.coverageStatus = status;
            const value = el('strong', String(coverage.summary[status + '_file_count']));
            value.dataset.coverageCount = status + '_file_count';
            box.append(value, el('span', label));
            counts.append(box);
        }
        const totals = el('p');
        for (const [key, label] of [['inventory_file_count', '인벤토리'], ['collected_file_count', '수집'], ['targeted_file_count', '분석 대상']]) {
            if (totals.childNodes.length) totals.append(document.createTextNode(' · '));
            const value = el('span', String(coverage.summary[key]));
            value.dataset.coverageCount = key;
            totals.append(document.createTextNode(label + ' '), value);
        }
        summary.append(el('h2', '분석 범위'), counts, totals,
            el('p', `수집 목록: ${coverage.scope.ignore_source} · 목록 밖 경로와 건수는 집계되지 않았습니다.`, 'muted'),
            el('p', '완료는 선택된 분석 절차가 관측된 오류 없이 끝났다는 뜻이며, 모든 관계를 발견했다는 보증은 아닙니다.', 'muted'));
        const search = $('coverage-search'), statusFilter = $('coverage-status-filter'), analyzerFilter = $('coverage-analyzer-filter');
        for (const [status, label] of Object.entries(labels)) {
            const option = el('option', label);
            option.value = status;
            statusFilter.append(option);
        }
        for (const producer of coverage.analyzers) {
            const option = el('option', producers[producer.analyzer_id] || producer.analyzer_id);
            option.value = producer.analyzer_id;
            analyzerFilter.append(option);
        }
        let built = false, currentPage = 0, indexed = [], matches = [];
        const reasonText = reason => `${reason.code}: ${reason.message}` + (reason.span ? ` (${reason.span.file_path}:${reason.span.start_line}-${reason.span.end_line})` : '');
        function draw() {
            const host = $('coverage-list');
            host.replaceChildren();
            currentPage = Math.max(0, Math.min(currentPage, Math.max(0, Math.ceil(matches.length / 50) - 1)));
            const fragment = document.createDocumentFragment();
            for (const item of matches.slice(currentPage * 50, (currentPage + 1) * 50)) {
                const row = el('tr');
                row.dataset.coverageRow = item.file.file_path;
                row.append(el('td', item.file.file_path, 'coverage-path'), el('td', labels[item.file.status]),
                    el('td', item.file.results.map(result => `${producers[result.analyzer_id] || result.analyzer_id}: ${labels[result.status]}`).join('\n'), 'coverage-producers'),
                    el('td', item.reasons || '—', 'coverage-reasons'));
                fragment.append(row);
            }
            if (!matches.length) {
                const row = el('tr'), cell = el('td', '일치하는 파일 없음');
                cell.colSpan = 4;
                row.append(cell);
                fragment.append(row);
            }
            host.append(fragment);
            $('coverage-prev').disabled = currentPage === 0;
            $('coverage-next').disabled = (currentPage + 1) * 50 >= matches.length;
            $('coverage-page-label').textContent = `${currentPage + 1} / ${Math.max(1, Math.ceil(matches.length / 50))} · ${matches.length}개 파일`;
        }
        function filter() {
            if (!built) return;
            currentPage = 0;
            const query = search.value.toLocaleLowerCase();
            matches = indexed.filter(item => (!query || item.search.includes(query)) &&
                (statusFilter.value === 'all' || item.file.status === statusFilter.value) &&
                (analyzerFilter.value === 'all' || item.producers.has(analyzerFilter.value)));
            draw();
        }
        disclosure.addEventListener('toggle', () => {
            if (!disclosure.open || built) return;
            indexed = coverage.files.map(file => {
                const reasons = file.results.length
                    ? file.results.flatMap(result => result.reasons.map(reason => `${producers[result.analyzer_id] || result.analyzer_id}: ${reasonText(reason)}`)).join('\n')
                    : file.reasons.map(reasonText).join('\n');
                return {file, reasons, search: (file.file_path + '\n' + reasons).toLocaleLowerCase(), producers: new Set(file.results.map(result => result.analyzer_id))};
            });
            built = true;
            filter();
        });
        search.oninput = filter;
        statusFilter.onchange = analyzerFilter.onchange = filter;
        $('coverage-prev').onclick = () => { currentPage--; draw(); };
        $('coverage-next').onclick = () => { currentPage++; draw(); };
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
        renderCoverage();
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
        details = arch?.details || {};
        if (fileMode) {
            delete definitions.identifier_file_count;
            kinds.large_node[1] = '파일 전체 줄 수가 설정한 임계값을 넘습니다.';
            $('node-search').placeholder = '파일 이름 또는 경로';
            $('report-summary').append(el('p', '파일 간 경로는 함수 호출 연쇄를 보장하지 않습니다.', 'notice'));
        }
        nodeMap = new Map(nodes.map(n => [n.id, n]));
        detailMap = new Map((details.nodes || []).map(n => [n.id, n]));
        detailIncident = new Map();
        fileIncident = new Map();
        implementationEdges = new Map();
        implementationTargets = new Map();
        for (const edge of details.edges || []) if (edge.relation === 'IMPLEMENTED_BY') implementationTargets.set(edge.from_id, edge.to_id);
        for (const edge of details.edges || []) {
            if (edge.relation === 'IMPLEMENTED_BY') {
                const file = details.node_files?.[edge.to_id];
                if (file) {
                    if (!implementationEdges.has(file)) implementationEdges.set(file, []);
                    implementationEdges.get(file).push(edge);
                }
            }
            if (declarationEdge(edge)) continue;
            for (const id of new Set([edge.from_id, ...candidateTargets(edge), displayOwner(edge.from_id), ...candidateTargets(edge).map(displayOwner)].filter(Boolean))) {
                if (!detailIncident.has(id)) detailIncident.set(id, []);
                detailIncident.get(id).push(edge);
            }
            for (const file of new Set([details.node_files?.[edge.from_id], ...candidateTargets(edge).map(target => details.node_files?.[target])].filter(Boolean))) {
                if (!fileIncident.has(file)) fileIncident.set(file, []);
                fileIncident.get(file).push(edge);
            }
        }
        candidates = (bottlenecks?.candidates || []).filter(c => !fileMode || c.target.startsWith('file:'));
        byTarget = new Map();
        for (const c of candidates) {
            if (!byTarget.has(c.target)) byTarget.set(c.target, []);
            byTarget.get(c.target).push(c);
        }
        incident = new Map();
        for (const e of projectedEdges(arch?.edges || [])) {
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
            box.append(el('strong', arch ? String(nodes.filter(n => isFile(n) && data.categories[n.id] === key).length) : '—'), el('span', label));
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
