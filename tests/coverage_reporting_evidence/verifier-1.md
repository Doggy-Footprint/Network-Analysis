# Independent audit 1

Spec: cfa172d091b48e63 v2. Result: retry. Invocation: 1/2.
Current evidence: suite6, 1132 passed / 200 subtests passed, 718.09s.
Verifier read Tests and evidence only, not Implementation or injected code.

| obligation | disposition | evidence |
| --- | --- | --- |
| V01 | accepted | 21 normal partitions, four strict failures, three recovered ASTs, four existing NestJS diagnostic classes; independent status/code/message/span/sibling observations |
| V02 | accepted | nine exclusions, max/max+1, four original discovery exclusions, unrelated extension, empty input, existing/new output; independent code mapping and reader calls |
| V03 | open | TF03-AGGREGATE-REASONS and TF03-COMMON-VERSION |
| V04 | open | TF03-COMMON-VERSION; existing stage-set/conversion evidence otherwise sufficient |
| V05 | open | TF03-COMMON-VERSION; immutable serialized characterization/schema/fatal/legacy hash evidence otherwise sufficient |
| V06 | open | TF06-SCOPE-LIMITATION; existing visible status/producer/reason/security/paging evidence otherwise sufficient |
| V07 | accepted | exact20 counters, seven read guards; 5 fresh 10k/7producer browser contexts; medians477.28/77.12/6.61/9.56/10.09/33.08ms; existing benchmark79.11s |
| V08 | accepted | repeatable main architecture review corroborated by independent counters and characterization; does not cover the V03 wire gaps |

## Findings

- TF03-AGGREGATE-REASONS: V03/F04/Q01/C07. The shuffled two-reason fixture checks output equality/cardinality but not supplied aggregate code/message/span. Removing span only from files[].reasons can escape while producer results remain correct. Exact supplied reason contents must be observed in the same fixture.
- TF03-COMMON-VERSION: V03/V04/V05, Signatures/F06/Q01/Q03/C07/C10. Production coverage.version is never independently asserted; omitting it or returning2 can escape mutually derived equalities. Required value is1.
- TF06-SCOPE-LIMITATION: V06/F07/Q04/C11/C13. assert_summary accepts any occurrence of 집계 or a raw not_enumerated token. Removing the actual limitation while retaining a generic tally label can escape. Observe the meaning that unlisted paths/counts are not enumerated, without imposing new scope.

No spec challenge or added Cartesian/structure target. Prior six correction dispositions remain supported and are not reopened. Proposed strongest mutation classes: duplicate producer accounting; recovered AST misreported complete; coverage information lost at propagation/export. Aggregate-span loss was proposed, not executed by the verifier.
