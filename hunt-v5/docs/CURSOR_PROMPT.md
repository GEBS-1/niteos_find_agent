Работай в этом репозитории как senior full-stack engineer. Сначала прочитай README.md и docs/ARCHITECTURE.md.

Это NITEOS Hunt V2. Критическое правило: NO SOURCE = NO FACT.

Не возвращай архитектуру к LLM-first поиску. LLM запрещено использовать для factual resolution владельца, ИНН/ОГРН, учредителя, директора, долей владения, телефона, email и соцпрофилей.

Вертикальный pipeline должен оставаться:
object → cadastre → owner/INN → company registry → recursive ownership graph → human owners/directors → sourced public professional contacts → verified card.

При подключении нового внешнего источника:
1. реализуй provider adapter;
2. нормализуй ответ в dataclass из app/providers/base.py;
3. бизнес-логика не должна зависеть от schema внешнего API;
4. сохраняй source/source_url;
5. пиши тесты;
6. запускай pytest.

Реальный кадастровый provider адаптируй в app/providers/cadastre_http.py. Не создавай mock/fake значения в production mode. Demo provider используется только при DEMO_MODE=1.
