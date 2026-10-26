# CSV row evidence implementation plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task by task.

**Goal:** Implement faithful CSV row capture, stable identities, and persisted text evidence for the competition.

**Architecture:** Add one source module following the existing captured-content adapter and projection pattern. Reuse the registry, transport, ingestion and Memory persistence without changing their behavior.

**Tech Stack:** Python 3.12, csv, urllib.parse, Pydantic, existing PowerContext Source Definition APIs.

**Spec:** `competition/challenges/source-01-table-evidence/instruction.md`

## Global Constraints

- No new runtime dependencies or network/model calls.
- Preserve exact strings, column order, UTF-8 and standard-library strict CSV semantics.
- Identity is `csv:{quote(document_id, safe='')}:{quote(primary_key_value, safe='')}`, at most 256 characters.
- Definition `csv-row`, version `1`; captured rows; standard text-evidence projection with exactly the five documented metadata fields.
- Leave all official competition assets unchanged. Start from the frozen baseline and official contest assets.

## Review Focus

- Encoded Unicode identity at the 256-character boundary.
- Header-only input still rejects an invalid document ID or missing primary key.
- Quoted empty fields differ from completely empty records.
- Direct row inputs reject inconsistent widths, key values or duplicate columns.
- CSV parser failures after valid records never expose partial rows.

### Task 1: CSV row capture and projection

**Files:** Create `src/powercontext/sources/csv_rows.py` and `tests/test_csv_rows.py`.

**Interfaces:** Consume Source, AdapterSourceDefinition and TextEvidence. Produce all models/functions/constants specified by the task, including `parse_csv_document(value) -> tuple[CSVRowInput, ...]` and `csv_row_source_id(document_id, primary_key_value) -> str`.

- [ ] Add focused boundary tests covering the review focus; use the official public test as the integration contract.
- [ ] Run focused and public tests before implementation; expect missing `powercontext.sources.csv_rows`.
- [ ] Implement strict decoding/parsing, validation, stable IDs, captured adapter readback and the standard projection in the new module.
- [ ] Run `make -C competition test-csv` plus focused tests; expect all pass including real runtime restart/citation lookup.
- [ ] Run existing source/observation tests and lint/type checks appropriate to the new module; commit the implementation and tests.

## Execution record

The existing WSL Python is 3.12.3. Its public networking resolves through the Windows proxy's fake DNS but cannot reach that proxy from NAT. Download the exact official Linux wheels through Windows and install offline; keep the official requirements unchanged.
