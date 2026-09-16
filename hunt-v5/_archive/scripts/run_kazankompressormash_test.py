import json
from app.providers.kazankompressormash_research import card

if __name__ == "__main__":
    print(json.dumps(card(), ensure_ascii=False, indent=2))
