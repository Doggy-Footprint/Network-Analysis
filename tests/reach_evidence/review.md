# untested_hub / isolated_node fixture review (V13)

Procedure: run `python -m code_analyzer -l <language> <fixture root> --bottlenecks out.json` (file granularity, default edge weights, `untested_hub_top_n` 10) on the four fixtures, list the `untested_hub` and `isolated_node` candidates, and check each against spec v5 R1–R7 by reading the source and the architecture JSON (`--json`).

| fixture | untested_hub | isolated_node | definition violations |
| --- | --- | --- | --- |
| futuramaapi | 3 | 0 | 0 |
| fastapi-realworld | 7 | 0 | 0 |
| android-nowinandroid | 4 | 1 | 0 |
| typescript-nestjs-realworld | 10 | 1 | 0 |

Checks:
- fastapi-realworld: `app.core.settings.app`, `app.models.common`, `app.core.logging`, `app.db.queries.queries` have no direct import in `tests/` (grep `from <module>`), consistent with no confirmed TESTS edge.
- android-nowinandroid: `SyncManager.kt` is referenced by no other file in the fixture (grep `SyncManager`), so it has no production edge. The three `*Entity.kt` hubs and `TopicNavKey.kt` carry only ambiguous TESTS edges (`uncertain_test_edge_count` 1–12), matching R3.
- typescript-nestjs-realworld: `index.js` holds only `require('./src/main')`, which the TS analyzer records as `dynamic_required`, so it is isolated with `dynamic_edge_count` 1 (R5, R6).
- typescript-nestjs-realworld: `src/tag/tag.controller.spec.ts` imports `./tag.entity`, but the TS analyzer emits no edge from the spec file (only 2 CONFIGURES edges). Uses inside top-level `describe` callbacks are not attributed to any symbol. `tag.entity.ts` is therefore an `untested_hub`. This follows the definition applied to the graph the analyzer produces; the missing edge is an analyzer input defect, recorded as F11 in `agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md`.

Result: 0 definition violations. One upstream analyzer defect (F11) inflates `untested_hub` for TypeScript test layouts.
