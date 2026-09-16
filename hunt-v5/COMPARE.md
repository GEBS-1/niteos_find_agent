# V5 vs prod Niteos

## Primary path (live)

Free, same idea as classic Niteos hunt:

- objects: Yandex `/maps/org` + 2GIS HTML + Nominatim
- photos/coords: Yandex org / Yandex Images / Nominatim
- legal entity: DaData + List-Org + open web (`legal_entity_match`, not EGRN deed)
- cadastre: NSPD soft timeout, or HTTP if `CADASTRE_API_URL` set

Maps API keys are **optional**.

## Archived (`_archive/`)

- 2GIS Places API provider
- one-off research fixtures / smoke HTML / scripts
- not imported by `app.main`

## Prod `app/`

Untouched. V5 is a parallel direction under `hunt-v5/`.
