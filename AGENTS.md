# Project Definition

Builds a repository's dependency network from analysis and surfaces its structural bottlenecks as refactoring candidates.
The network joins language-level relations with connections that only framework semantics reveal, such as dependency injection, routing, and ORM-to-migration links, etc. Recall takes priority over precision: uncertain relations stay in the network, graded by confidence and resolution and discounted by configurable edge weights, rather than being dropped.
The project does not simulate or predict AI agent behavior, and does not judge code quality, change risk, or task difficulty; a candidate is a structural fact for a human or agent to review, not a verdict.

<!-- harness:begin -->
@.harness/instructions/harness-block.md
<!-- harness:end -->
