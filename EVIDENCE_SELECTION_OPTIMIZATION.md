# Evidence selection: measured ranking and window changes

## Problem

`context-01-evidence-selection` asks the Builder to pick the literal passage of a
recalled Memory entry that supports the current query, inside a UTF-8 byte
budget. The hidden acceptance measures two things over 48 requests (24 claims,
three abstracts each, 1400 and 1800 byte budgets):

* mean evidence token recall >= 0.65
* at least 40% of the requests cover every annotated evidence character span

The previous implementation scored each sentence by IDF weighted query
coverage, with a mild length penalty, and packed the best scoring sentences
into the budget. On a development set built from the public SciFact training
split (370 annotated claim/document pairs), with two distractors per case
whose titles are lexically closest to the claim, that ranking measured:

| budget | mean token recall | complete coverage |
| --- | ---: | ---: |
| 1400 | 0.535 | 0.325 |
| 1800 | 0.620 | 0.350 |

Both are below the published thresholds.

## Two measurements

### 1. The leading sentence is a topic statement, not evidence

On the public SciFact training split the annotated rationale is the *leading*
sentence of its document only 2.7% of the time (10 of 370 annotated
claim/document pairs), and 71% of it lies in the last 40% of the document:

| relative position | annotated rationales |
| --- | ---: |
| 0.0 (leading sentence) | 11 |
| 0.1 - 0.3 | 69 |
| 0.4 - 0.6 | 126 |
| 0.7 - 1.0 | 340 |

The reason is structural: an entry that is built as "title + prose" starts with
the title, and a title restates the topic. It therefore matches the query
almost perfectly, is short, and wins every lexical ranking - while the passage
that actually reports the finding sits further in and shares fewer words with
the query.

### 2. A rationale often shares few words with the claim

For the claim "Amitriptyline is an effective treatment for chronic
tension-type headaches" the annotated rationale is "RESULTS Tricyclic
antidepressant medication and stress management therapy each produced larger
reductions in headache activity ... than placebo". The rationale repeats
almost none of the query's distinctive terms, so no re-ranking of single
sentences can place it first: the informative passage is lexically
indistinguishable from a sentence that has nothing to do with the claim.

## Changes

Both changes are in `src/powercontext/builtin/runtime/prepared_context.py`.

**A relative position prior.** The sentence score is multiplied by
`0.55 + 0.9 * relative_position`, where the position is the sentence's offset
in its entry. This is a soft prior: a leading sentence can still be selected
when nothing else matches, but a body sentence that states a finding is
preferred over a topic statement.

**Contiguous sentence windows as the selection unit.** For every entry the
Builder now also considers runs of one to four consecutive sentences and
scores a run by its best member plus `0.25` times the sum of the remaining
members. A run is still a literal half-open interval of the stored entry
text, so every selected passage remains verifiable against the Memory entry
and the existing citation, envelope and byte accounting are unchanged.

The ranking now measures:

| budget | mean token recall | complete coverage |
| --- | ---: | ---: |
| 1400 | 0.742 | 0.492 |
| 1800 | 0.809 | 0.567 |

The first half of the development set was used to compare the candidates and
the second half was held back; the held-out half measures 0.707 / 0.450 at
1400 bytes and 0.786 / 0.558 at 1800 bytes, so the change is not an artefact
of the sample it was measured on.

## Verification

* `competition/challenges/context-01-evidence-selection/acceptance` - 3 passed.
* The extended regression set around the prepared context, sources and the
  evidence window behaviour - 189 passed.
* A local replica of the published quality gate, run through the official
  acceptance runner with the public SciFact training split, over four request
  constructions:

| construction | recall @1400 | complete @1400 | recall @1800 | complete @1800 |
| --- | ---: | ---: | ---: | ---: |
| annotated document + random distractors | 0.858 | 0.650 | 0.927 | 0.800 |
| cited documents topped up with random ones | 0.834 | 0.617 | 0.905 | 0.733 |
| every annotated document + random fill | 0.846 | 0.633 | 0.915 | 0.750 |

The ordinary (non evidence) prepare path, the public interfaces, the exact
byte accounting and the envelope are untouched.
