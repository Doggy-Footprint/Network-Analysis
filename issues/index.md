File: a8c91e4b7d3f5a20-kotlin-parser-cache.md
Summary: Track sharing Kotlin AST parsing between Android extraction and Kotlin graph construction as a separate performance task.
Related Files: framework_analyzers/android/analyzer.py, language_analyzers/kotlin/analyzer.py
Related Symbols: AndroidAnalyzer, KotlinAnalyzer
---
File: e6cb320a150dc83a-fastapi-title-version-non-literal.md
Summary: FastAPI app title/version silently fall back to hardcoded defaults when set via a non-literal expression instead of a string constant.
Related Files: framework_analyzers/fastapi/analyzer.py, tests/test_analyzer.py
Related Symbols: FastAPIAnalyzer, _check_app_or_router_instantiation
---
File: ae981d8b41e02cab-fastapi-absolute-import-router-prefix.md
Summary: Router prefix resolution fails and is silently dropped when project source uses absolute imports rooted at its own package name.
Related Files: framework_analyzers/fastapi/analyzer.py, tests/test_analyzer.py
Related Symbols: FastAPIAnalyzer, _resolve_target_router_module, _resolve_router_hierarchy
