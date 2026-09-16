from dataclasses import dataclass

@dataclass
class UltimateOwner:
    full_name: str
    effective_share: float | None
    source: str
    path: list[str]

async def resolve_ultimate_owners(root_inn,company_fetcher,max_depth=8):
    owners=[]
    async def walk(inn,multiplier,depth,path,visited):
        if depth>max_depth or inn in visited: return
        company=await company_fetcher(inn)
        if not company: return
        visited=set(visited); visited.add(inn)
        for founder in company.founders:
            share=founder.share_percent
            eff=None if multiplier is None or share is None else multiplier*(share/100)
            next_path=path+[company.name]
            if founder.kind=="person":
                owners.append(UltimateOwner(founder.name,None if eff is None else round(eff*100,4),founder.source or company.source,next_path))
            elif founder.kind=="company" and founder.inn:
                await walk(founder.inn,eff,depth+1,next_path,visited)
    await walk(root_inn,1.0,0,[],set())
    merged={}
    for owner in owners:
        key=owner.full_name.strip().lower()
        if key not in merged: merged[key]=owner
        elif merged[key].effective_share is not None and owner.effective_share is not None:
            merged[key].effective_share=round(merged[key].effective_share+owner.effective_share,4)
    return sorted(merged.values(),key=lambda x:(x.effective_share is not None,x.effective_share or -1),reverse=True)
