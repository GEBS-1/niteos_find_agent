# Production pipeline: building → facade → owner → decision-maker → proposal

1. Search physical buildings with 2GIS/OSM/Yandex Places provider.
2. Resolve exact address + coordinates.
3. VisualEvidenceProvider:
   - retain a sourced facade photo if available;
   - geocode exact building;
   - provide Yandex Maps street/panorama link;
   - if `YANDEX_MAPS_API_KEY` exists, frontend may initialize Panorama API at those coordinates;
   - optional image-search adapter can return public/licensed facade photos with source URLs.
4. Cadastre provider maps address/coordinates to cadastral object. Multiple candidates require review.
5. Property owner comes only from cadastral/property source. No heuristic company guess.
6. Company provider resolves INN/OGRN/director/founders/finance.
7. People engine prioritizes: chief engineer → technical director → chief power engineer → facility/operations director → general director → owner.
8. Contact engine searches each known person separately and accepts only public professional contact evidence. Company phones never become personal phones.
9. Only after all facts are assembled, OpenAIProposalEngine may inspect the facade photo and generate a lighting concept + short commercial proposal.

## Recommended APIs

- 2GIS Places API: object/building discovery, address, geometry, contacts, ITIN where available.
- Yandex Maps JS API Panoramas: interactive street-level facade inspection. Do not scrape panorama tiles.
- DaData / Kontur / other legitimate registry provider: company enrichment.
- A legitimate cadastral/property API: cadastral number and available legal-entity owner information.
- Public web/image search API: official pages, professional profiles, public facade images.
- OpenAI Responses API: facade analysis and proposal only.
