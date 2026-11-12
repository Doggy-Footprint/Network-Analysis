# Project Definition

Builds a repository's dependency network from analysis and surfaces, as review candidates, its structural bottlenecks and the code problems a change introduces, weighted toward problems reported to arise from AI coding agents.
The network joins language-level relations with connections that only framework semantics reveal, such as dependency injection, routing, and ORM-to-migration links, etc. Recall takes priority over precision: uncertain relations and findings stay in the output, graded by confidence and resolution and discounted by configurable edge weights, rather than being dropped.
Candidates cover structure, code quality, security, and correctness. The project does not simulate or predict AI agent behavior, and does not score change risk or task difficulty; a candidate is evidence for a human or agent to review, not a verdict.

<!-- harness:begin -->
@.harness/instructions/harness-block.md
<!-- harness:end -->
