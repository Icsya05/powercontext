# Query-coverage window optimization

Binding spec: competition/challenges/context-01-evidence-selection/instruction.md.
User authorized direct optimization until14:00 Beijing, retaining the earlier10%remaining quota stop.

## Design

The long-sentence fallback currently centers a literal window on the first highest-weight query occurrence. An early isolated occurrence can hide a later cluster containing all query terms. Preserve literal offsets/citations and exact UTF8 budgeting; select among bounded high-coverage query clusters, compare actual fitted windows by query coverage, and retain deterministic ties. No evaluation labels, sample IDs, dependencies, online models or official assets are used.

## Steps

1. Reproduce early-isolated/late-cluster misses with independent synthetic input, observe RED.
2. Implement bounded query-cluster anchor selection and exact fitting; verify GREEN plus existing evidence/prepared/incremental/probe regressions.
3. Measure old/new selection on independent generated cases, record byte budgets, query coverage and latency (not hidden evidence quality).
4. Independent review; fix concrete findings; verify complete public integration, commit and push before14:00.

## Ledger

- Start2677f566 / code39a12dbf. Existing95public+251focused/13skip passed.
- Ruling: improve a demonstrated local query-coverage failure; no claim that this establishes hidden SciFact evidence recall/completeness.

- RED threebudgets→GREEN; firstindependentreviewfoundzero-querymid-gapregression. Addedfailingpublicguard; byte-awareclusterbound+occurrencefallback+positivecoveragefix.
- Unicodeenvelopeline-separatortestRED→GREEN. Finalcode d458a7f3:316relatedpass/13skip, Ruff/format/tyclean. Independent64cases querycoverage.4375→.9375 withnoindividualdrop; p50.68→3.46ms. Hiddenqualityunverified; floatingpointnear-tieMinor deferred. Wholepublicsuitependingcompletion.

- Final:d458a7f3 frozenmirrorfull95publicGREEN and316relatedGREEN/13skip;sourceRuff/format/tyclean. UTF8JSONseparators3charactersescapedandbudgetaccounted. Floatingpointnear-tieMinor deferred; hiddenSciFactunverified. Independentpackingtradeoffreproducedbutnotimplemented. Finalstophandoffpreparedfor14:00.
