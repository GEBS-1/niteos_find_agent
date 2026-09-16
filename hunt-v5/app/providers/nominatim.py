import httpx
from app.config import settings
from app.providers.base import ObjectCandidate

class NominatimObjectProvider:
    BASE="https://nominatim.openstreetmap.org/search"
    async def search(self,city,query,count):
        params={"q":f"{query}, {city}","format":"jsonv2","addressdetails":1,"limit":min(max(count*2,10),50),"countrycodes":"ru"}
        async with httpx.AsyncClient(timeout=20,headers={"User-Agent":settings.user_agent}) as client:
            r=await client.get(self.BASE,params=params); r.raise_for_status(); rows=r.json()
        out=[]; seen=set()
        for row in rows:
            display=row.get("display_name") or ""; lat=float(row["lat"]) if row.get("lat") else None; lon=float(row["lon"]) if row.get("lon") else None
            key=(round(lat or 0,5),round(lon or 0,5),display.lower())
            if key in seen: continue
            seen.add(key)
            osm_type=row.get("osm_type") or "node"; osm_id=row.get("osm_id") or ""
            out.append(ObjectCandidate(external_id=f"osm-{osm_type}-{osm_id}",name=row.get("name") or display.split(",")[0].strip(),address=display,lat=lat,lon=lon,category=row.get("type") or row.get("class") or "",source_url=f"https://www.openstreetmap.org/{osm_type}/{osm_id}",source_provider="nominatim"))
            if len(out)>=count: break
        return out
