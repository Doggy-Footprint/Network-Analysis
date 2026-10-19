# untested_hub / isolated_node fixture review (V13)

Procedure (repeatable): `PYTHONPATH=. uv run -q --with-requirements requirements-dev.txt python tests/reach_evidence/review_candidates.py <scratch dir>` runs each fixture with the commands used by `tests/reach_evidence/make_base_manifest.py` (file granularity, default edge weights, `untested_hub_top_n` 10), writes the bottleneck JSON and the architecture JSON (`--json`), and prints one row per `untested_hub` / `isolated_node` candidate.

For each candidate it records the product-side evidence (confirmed and uncertain incoming TESTS edges for hubs; every edge touching the file and the count of static production connections for isolated files) and an independent text check (test files, or other production source files, whose text mentions the file stem). A row is consistent when the product evidence satisfies spec v6 R1–R6 (no confirmed TESTS edge; no static exact/unique_name connection to another production file). Text mentions without an edge were opened by hand.

Guessed defects targeted (experience-based): uncertain TESTS edges treated as confirmed; tests that import a hub but produce no edge; isolation caused by an edge the product drops; test/vendored/boundary neighbours counted as connections; wrong framework flag changing the graph.

Hand-opened mentions:
- futuramaapi `db/session.py`: `tests/conftest.py` mentions `session` only as a local variable and a `mock.patch` string target in `routers.services._base.session_manager`; it does not import `futuramaapi.db.session`.
- futuramaapi `helpers/pydantic.py`: the test imports the third-party `pydantic` package, not the helper module.
- fastapi-realworld `db/queries/queries.py`: the test imports `app.db.queries.tables`, a sibling module.
- fastapi-realworld `models/domain/profiles.py`: the tests import `app.db.repositories.profiles` and `app.models.schemas.profiles`, not the domain module.
- fastapi-realworld `core/settings/app.py`: `app` matches the package name in every test; the only `app.core` import is `app.core.config`.
- typescript-nestjs-realworld `tag/tag.entity.ts`: `src/tag/tag.controller.spec.ts` imports `./tag.entity`, but the TypeScript analyzer emits no edge from the spec file (uses inside top-level `describe` callbacks are not attributed). This is an analyzer input defect, recorded as F11 in `agent-docs/handoff/dad85e4830f21190-existing-signal-defects.md`; the candidate follows the definition on the produced graph.

## futuramaapi (`-l python`)

| kind | target | product evidence | independent text check | consistent |
| --- | --- | --- | --- | --- |
| untested_hub | `futuramaapi/db/session.py` | rank 10, confirmed TESTS 0, uncertain 0 | test files mentioning `session`: 1 (tests/conftest.py) | yes (name mention without resolved edge) |
| untested_hub | `futuramaapi/helpers/pydantic.py` | rank 2, confirmed TESTS 0, uncertain 0 | test files mentioning `pydantic`: 1 (tests/unit/routers/services/characters/test_get_character.py) | yes (name mention without resolved edge) |
| untested_hub | `futuramaapi/helpers/templates.py` | rank 3, confirmed TESTS 0, uncertain 0 | test files mentioning `templates`: 0 | yes |

## fastapi-realworld (`-l python`)

| kind | target | product evidence | independent text check | consistent |
| --- | --- | --- | --- | --- |
| untested_hub | `app/core/logging.py` | rank 8, confirmed TESTS 0, uncertain 0 | test files mentioning `logging`: 0 | yes |
| untested_hub | `app/core/settings/app.py` | rank 3, confirmed TESTS 0, uncertain 0 | test files mentioning `app`: 14 (tests/conftest.py, tests/test_api/test_errors/test_422_error.py) | yes (name mention without resolved edge) |
| untested_hub | `app/core/settings/base.py` | rank 5, confirmed TESTS 0, uncertain 0 | test files mentioning `base`: 0 | yes |
| untested_hub | `app/db/queries/queries.py` | rank 10, confirmed TESTS 0, uncertain 0 | test files mentioning `queries`: 1 (tests/test_db/test_queries/test_tables.py) | yes (name mention without resolved edge) |
| untested_hub | `app/db/repositories/base.py` | rank 4, confirmed TESTS 0, uncertain 0 | test files mentioning `base`: 0 | yes |
| untested_hub | `app/models/common.py` | rank 6, confirmed TESTS 0, uncertain 0 | test files mentioning `common`: 0 | yes |
| untested_hub | `app/models/domain/profiles.py` | rank 7, confirmed TESTS 0, uncertain 0 | test files mentioning `profiles`: 2 (tests/test_api/test_routes/test_articles.py, tests/test_api/test_routes/test_profiles.py) | yes (name mention without resolved edge) |

## android-nowinandroid (`-l kotlin`)

| kind | target | product evidence | independent text check | consistent |
| --- | --- | --- | --- | --- |
| isolated_node | `core/data/src/main/kotlin/com/google/samples/apps/nowinandroid/core/data/util/SyncManager.kt` | 27 lines, edges touching 0 (none), static production connections 0 | other production files mentioning `SyncManager`: 0 | yes |
| untested_hub | `core/database/src/main/kotlin/com/google/samples/apps/nowinandroid/core/database/model/NewsResourceFtsEntity.kt` | rank 7, confirmed TESTS 0, uncertain 7 | test files mentioning `NewsResourceFtsEntity`: 0 | yes |
| untested_hub | `core/database/src/main/kotlin/com/google/samples/apps/nowinandroid/core/database/model/RecentSearchQueryEntity.kt` | rank 9, confirmed TESTS 0, uncertain 1 | test files mentioning `RecentSearchQueryEntity`: 0 | yes |
| untested_hub | `core/database/src/main/kotlin/com/google/samples/apps/nowinandroid/core/database/model/TopicFtsEntity.kt` | rank 4, confirmed TESTS 0, uncertain 9 | test files mentioning `TopicFtsEntity`: 0 | yes |
| untested_hub | `feature/topic/api/src/main/kotlin/com/google/samples/apps/nowinandroid/feature/topic/api/navigation/TopicNavKey.kt` | rank 6, confirmed TESTS 0, uncertain 12 | test files mentioning `TopicNavKey`: 0 | yes |

## typescript-nestjs-realworld (`-l typescript -f nestjs`)

| kind | target | product evidence | independent text check | consistent |
| --- | --- | --- | --- | --- |
| isolated_node | `index.js` | 2 lines, edges touching 1 (IMPORTS/dynamic_required), static production connections 0 | other production files mentioning `index`: 0 | yes |
| untested_hub | `src/article/article.entity.ts` | rank 1, confirmed TESTS 0, uncertain 0 | test files mentioning `article.entity`: 0 | yes |
| untested_hub | `src/article/comment.entity.ts` | rank 3, confirmed TESTS 0, uncertain 0 | test files mentioning `comment.entity`: 0 | yes |
| untested_hub | `src/article/dto/create-article.dto.ts` | rank 9, confirmed TESTS 0, uncertain 0 | test files mentioning `create-article.dto`: 0 | yes |
| untested_hub | `src/article/dto/create-comment.ts` | rank 8, confirmed TESTS 0, uncertain 0 | test files mentioning `create-comment`: 0 | yes |
| untested_hub | `src/profile/follows.entity.ts` | rank 10, confirmed TESTS 0, uncertain 0 | test files mentioning `follows.entity`: 0 | yes |
| untested_hub | `src/tag/tag.entity.ts` | rank 6, confirmed TESTS 0, uncertain 0 | test files mentioning `tag.entity`: 1 (src/tag/tag.controller.spec.ts) | yes (analyzer emits no edge from these test files: F11) |
| untested_hub | `src/user/dto/create-user.dto.ts` | rank 5, confirmed TESTS 0, uncertain 0 | test files mentioning `create-user.dto`: 0 | yes |
| untested_hub | `src/user/dto/login-user.dto.ts` | rank 7, confirmed TESTS 0, uncertain 0 | test files mentioning `login-user.dto`: 0 | yes |
| untested_hub | `src/user/dto/update-user.dto.ts` | rank 4, confirmed TESTS 0, uncertain 0 | test files mentioning `update-user.dto`: 0 | yes |
| untested_hub | `src/user/user.entity.ts` | rank 2, confirmed TESTS 0, uncertain 0 | test files mentioning `user.entity`: 0 | yes |

Result: 27 candidates reviewed, 0 definition violations, 1 upstream analyzer defect (F11).
