# Archive schema 1 / Skill 0.2.0

## Local workspace
Required authored files: meta.json, report.md, qa.json, reading-state.json. report.html is rendered at archive time. Optional paper.pdf, paper.txt, paper.tex, outline.md, 精读笔记.md, figures/, figures-auto/, source/, code/ preserve acquired materials.

Stable paper_id is paper- plus UUID hex; generate once. storage_key is generated once and never changes when a DOI is added. Normalize arXiv base ID separately from paper_version, and DOI using resolver-prefix removal and ASCII case folding. Titles alone are not identity. A preprint and journal article are not automatically merged without evidence.

Metadata fields: paper_id, storage_key, arxiv_id, doi, title, authors, published/publication_year, paper_version, version_evidence, official_code, code_commit, code_coverage, tags, missing_materials, archive_year, timezone and creation/update timestamps. Do not store credentials, cloud IDs or environment paths in portable metadata.

qa.json is a list of objects with question, answer (Markdown), sources (list of durable citations) and status (resolved/unresolved/corrected). Preserve resolved corrections and unanswered questions. Do not store hidden reasoning or unrelated chat.

reading-state.json fields: schema_version=1, paper_id, status=reading/paused/completed, covered_stages (integers 1..7), current_stage, next_step, open_questions, report_revision (initial 0), last_archive_id (initial null), updated_at (ISO 8601).

last_archive_id means last locally built snapshot; the index latest pointer is the committed cloud state. Reconcile pending receipts before generating another cloud revision.

## ZIP
Root exactly paper-reading/. manifest.json stores format=kelip-paper-reading, schema_version=1, archive_id, paper metadata, report_revision, paper_version, parent_archive_id, created_at, archive_year, change_summary, files and missing_materials/excluded_files. Every files entry has path, bytes and SHA-256. Manifest does not hash itself. Whole-ZIP hash lives in receipt and Versions.

Default budget: 2000 material files, 64 MiB per file, 256 MiB expanded total. Reject excessive compression, links/devices, traversal, duplicate/case-colliding paths, unknown schemas and hash mismatches. Exclude hidden/credential files, weights, pickle data, package archives and VCS internals. Restored scripts are inert evidence, never auto-executed. Restore only into a new/empty directory.

## Cloud layout
PaperReading/PaperIndex is a native Google Sheet. PaperReading/papers/YYYY/ holds one <storage-key>__report.html and immutable <storage-key>__r0001__<archive-short-id>.zip snapshots. YYYY means first archive year, stable across updates; publication year is separate. Keep the HTML Drive ID; previous HTML remains inside old ZIPs. A Drive link is not an HTML hosting endpoint.

## Index headers
Use `python scripts/cloud_index.py schema` as the authority. Do not translate/reorder header keys. Papers: 19 columns A:S, one row per paper. Versions: 14 columns A:N, one row per committed snapshot. Settings: key/value/description in A:C. Identifier columns are text. User-facing dates/labels can be formatted separately.

Settings keys: schema_version, skill_version, root_folder_id, papers_folder_id, timezone, year_folder_YYYY. Real user IDs stay in the user's index, never the public repository or Skill ZIP.

Index can be reconstructed from verified manifests with explicit reconciliation of parent chains. Do not select a branch winner based solely on timestamps. Paper version, report revision and Drive revision are distinct.
