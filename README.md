# UniDPP papers
Position and technical contributions for ISO/IEC JTC 5 (inaugural
meeting and workstream inputs). Pipeline per oimlsmart/idta-dpp
(branded HTML → PDF). Catalogue: the UniDPP papers catalogue, items 1–6.

## Freshness

Every rendered PDF records its provenance in `MANIFEST.json` — the
`unidpp-spec` commit it was built against (recorded at build time by
`build-papers-pdf.py`). The refresh trigger the papers lacked:

```sh
python3 build-papers-pdf.py --check-fresh
```

exits non-zero when any paper predates the current specification
head — a material specification change re-renders the affected
papers in the same change. (The seven current papers predate the
correlation and consumer-edge clauses; re-rendering them is the
standing residue the check names.)
