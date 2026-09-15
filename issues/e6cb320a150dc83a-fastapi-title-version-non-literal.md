# FastAPI app title/version silently default on non-literal expressions

`FastAPIAnalyzer._check_app_or_router_instantiation` (`framework_analyzers/fastapi/analyzer.py`) only extracts `title=`/`version=` when the keyword value is an `ast.Constant`. When an app builds `FastAPI(**settings.fastapi_kwargs)` or `FastAPI(title=settings.PROJECT_NAME, ...)`, extraction falls through to the hardcoded defaults (`"FastAPI App"` / `"0.1.0"`) with no signal that the real value was unresolved.

Confirmed against both registered FastAPI fixtures (`fixtures/registry.py`: `fastapi-realworld`, `fastapi-official-template`) while writing `tests/test_analyzer.py::FastAPIRealFixtureSmokeTests` — both apps hit this path, and the tests now pin the degraded default as documented current behavior rather than the real title/version.

Consider distinguishing "no title/version given" from "title/version given but not statically resolvable" in the emitted profile, so downstream consumers don't treat a silent default as a real app name.
