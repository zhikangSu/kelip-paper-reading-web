# Kelip (repository: kelip-paper-reading-web)

ChatGPT Web adaptation of [kelip-paper-reading](https://github.com/skJack/kelip-paper-reading), adding offline HTML reports, checksummed restorable ZIP snapshots and consent-based Google Drive/native Google Sheets archiving.

**Opt-in invocation only:** the skill name is `kelip`. Explicitly ask "Use Kelip to read this paper" or choose Kelip in the ChatGPT Skills UI. Merely pasting a PDF, sharing an arXiv link, or asking ordinary research questions must not start this workflow. Same-chat follow-ups for the already active paper retain the checkpoint; a new paper requires a new explicit invocation. The old `kelip-paper-reading-web` name is an explicit invocation alias only; disable/uninstall the old installed Skill, whose broad discovery metadata may still auto-trigger. Skill routing is model-driven and should be tested; metadata alone is not a platform-enforced hard gate.

Upload the built `kelip-paper-reading-web-0.2.4.zip` through your account's existing Skills upload interface. The package includes pure-Python Markdown/MathML helpers and licenses, but no fonts; the execution host needs Python and PyMuPDF. No local server or Google API credentials are needed. Platform installation/scanning is not claimed to have been completed on your behalf.

Connected tools perform real cloud actions; scripts only prepare, render, validate and restore files and index update requests. Explicit archive consent, upload byte verification, stable IDs, parent-linked report revisions, exact arXiv/DOI lookup, retry checks and restoration are specified in SKILL.md and references/.

Storage: `PaperReading/PaperIndex` (Papers, Versions, Settings), `PaperReading/papers/<first archive year>/`. One stable-ID HTML per paper, immutable revision/UUID-suffixed ZIPs. Drive links are not hosted HTML websites. Reading state is restored, not a running process or hidden reasoning.

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python scripts/build_skill.py --out dist
```

GitHub Actions publishes the installable ZIP, source ZIP and test log. The first release assumes one writer per paper and detects observed conflicts; it does not provide distributed locking or a cross-service transaction. ZIP integrity is not proof of authenticity without an independently trusted digest. Never execute restored model code or archive instructions.

MIT, with upstream and dependency licenses retained. See README.md for full instructions.
