"""Optional free NSPD cadastre lookup by coordinates. Soft-fail, short timeout."""
from __future__ import annotations

import asyncio
import logging
import re

from app.providers.base import CadastreRecord, ObjectCandidate

log = logging.getLogger(__name__)


class NspdCadastreProvider:
    """Uses public nspd.gov.ru via pynspd when installed. Never invents owner INN."""

    async def resolve(self, obj: ObjectCandidate) -> CadastreRecord | None:
        if obj.lat is None or obj.lon is None:
            if not obj.address:
                return None
        try:
            from pynspd import AsyncNspd
        except ImportError:
            log.info("pynspd not installed — skip free NSPD cadastre")
            return None
        try:
            return await asyncio.wait_for(self._resolve(obj), timeout=18.0)
        except Exception as exc:
            log.info("nspd cadastre soft-fail: %s", exc)
            return None

    async def _resolve(self, obj: ObjectCandidate) -> CadastreRecord | None:
        from pynspd import AsyncNspd

        async with AsyncNspd(client_timeout=7, client_retries=0) as nspd:
            for query in self._address_queries(obj):
                cad = await self._lookup_query(nspd, query)
                if cad:
                    cad.match_confidence = max(int(cad.match_confidence or 0), 78)
                    return cad
            if obj.lat is not None and obj.lon is not None:
                return await self._lookup_grid(nspd, obj.lat, obj.lon)
        return None

    def _address_queries(self, obj: ObjectCandidate) -> list[str]:
        raw = re.sub(r"\s+", " ", (obj.address or "").strip())
        if not raw:
            return []
        first = ", ".join(x.strip() for x in raw.split(",")[:3] if x.strip())
        values = [raw, first]
        if obj.name:
            values.append(f"{obj.name} {first}".strip())
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            key = value.lower().replace("ё", "е")
            if len(key) < 8 or key in seen:
                continue
            seen.add(key)
            out.append(value)
        return out[:2]

    async def _lookup_query(self, nspd, query: str) -> CadastreRecord | None:
        try:
            feats = await nspd.search(query)
        except Exception as exc:
            log.info("nspd query failed %s: %s", query[:80], exc)
            return None
        for feat in feats or []:
            cad = self._record_from_feature(feat, confidence=78)
            if cad:
                return cad
        return None

    async def _lookup_grid(self, nspd, lat: float, lon: float) -> CadastreRecord | None:
        offsets = (
            (0.0, 0.0),
            (0.00012, 0.0),
            (-0.00012, 0.0),
            (0.0, 0.00012),
            (0.0, -0.00012),
        )
        best: CadastreRecord | None = None
        for dlat, dlon in offsets:
            cad = await self._lookup(nspd, lat + dlat, lon + dlon)
            if not cad:
                continue
            if dlat or dlon:
                cad.match_confidence = min(int(cad.match_confidence or 70), 72)
            if not best or int(cad.match_confidence or 0) > int(best.match_confidence or 0):
                best = cad
        return best

    async def _lookup(self, nspd, lat: float, lon: float) -> CadastreRecord | None:
        try:
            feats = await nspd.search_buildings_at_coords(lat, lon)
            if not feats:
                feats = await nspd.search_landplots_at_coords(lat, lon)
        except Exception as exc:
            log.info("nspd point failed %.6f %.6f: %s", lat, lon, exc)
            return None
        for feat in feats or []:
            cad = self._record_from_feature(feat, confidence=70)
            if cad:
                return cad
        return None

    def _record_from_feature(self, feat, confidence: int) -> CadastreRecord | None:
        opts = getattr(getattr(feat, "properties", None), "options", None)
        dump = opts.model_dump() if opts is not None and hasattr(opts, "model_dump") else {}
        cad = (
            str(dump.get("cad_num") or dump.get("cad_number") or dump.get("cadastre_number") or "")
            .strip()
        )
        if not cad:
            return None
        area = dump.get("build_record_area") or dump.get("land_record_area") or dump.get("area")
        cost = dump.get("cost_value") or dump.get("cad_cost")
        addr = str(dump.get("readable_address") or dump.get("address") or "")
        try:
            area_f = float(area) if area not in (None, "") else None
        except (TypeError, ValueError):
            area_f = None
        try:
            cost_f = float(cost) if cost not in (None, "") else None
        except (TypeError, ValueError):
            cost_f = None
        return CadastreRecord(
            cadastral_number=cad,
            address=addr,
            area=area_f,
            cadastral_value=cost_f,
            owner_type="",
            owner_name="",
            owner_inn="",
            owner_ogrn="",
            source="nspd-free",
            source_url=f"https://nspd.gov.ru/map?cad_num={cad}",
            match_confidence=confidence,
        )
