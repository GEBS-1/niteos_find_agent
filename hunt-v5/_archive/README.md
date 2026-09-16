# Archive — not the primary hunt path

Moved out of the live app so the free pipeline stays clean:

- `providers/twogis.py` — 2GIS Places API (needs key; free HTML path is primary)
- `providers/kazankompressormash_research.py` — one-off research fixture
- `providers/real_kazan_fixture.py` — one-off research fixture
- `scripts/run_*_test.py` — smoke runners for those fixtures
- `tests/test_*_research.py` — fixture tests
- `static/real-test*.html` — static smoke cards

Restore only if you explicitly need an API/fixture experiment.
