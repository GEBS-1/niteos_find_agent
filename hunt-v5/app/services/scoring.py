from app.providers.base import ContactCandidate

def score_contact(c: ContactCandidate):
    score=0
    if c.name_match: score+=30
    if c.company_match: score+=30
    if c.role_match: score+=15
    if c.city_match: score+=10
    if c.explicit_person_link: score+=15
    return score, "confirmed" if score>=90 else "probable" if score>=70 else "unverified"
