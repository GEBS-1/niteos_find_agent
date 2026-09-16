const $ = s => document.querySelector(s);
const esc = s => (s ?? '').toString().replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
const money = n => n == null ? '-' : n >= 1e9 ? (n / 1e9).toFixed(1) + ' млрд ₽' : n >= 1e6 ? (n / 1e6).toFixed(0) + ' млн ₽' : Number(n).toLocaleString('ru-RU') + ' ₽';
const link = (url, label = 'Источник') => url ? `<a class="inline-link" href="${esc(url)}" target="_blank" rel="noreferrer">${esc(label)}</a>` : '';
const contactScope = c => c.contact_scope === 'personal' ? 'личный контакт' : c.contact_scope === 'public_work_contact' ? 'рабочий контакт ЛПР' : c.contact_scope === 'public_object_contact' ? 'контакт объекта' : 'публичный контакт';
const role = r => ({
  chief_engineer: 'Главный инженер',
  technical_director: 'Технический директор',
  chief_power_engineer: 'Главный энергетик',
  facility_director: 'Директор по эксплуатации',
  operations_director: 'Директор по производству',
  general_director: 'Генеральный директор',
  ultimate_identified_owner: 'Конечный владелец'
}[r] || r || 'ЛПР');

const BUILDING_TYPES = [
  'бизнес центр',
  'торговый центр',
  'гостиница',
  'отель',
  'офисное здание',
  'административное здание',
  'производственный комплекс',
  'складской комплекс',
  'медицинский центр',
  'автосалон',
  'ресторан отдельное здание',
  'банк отдельное здание'
];
const GEO = {
  city: [
    'Казань', 'Самара', 'Москва', 'Санкт-Петербург', 'Екатеринбург', 'Новосибирск',
    'Краснодар', 'Нижний Новгород', 'Тольятти', 'Набережные Челны', 'Альметьевск',
    'Уфа', 'Пермь', 'Саратов', 'Челябинск', 'Тюмень', 'Сочи', 'Ростов-на-Дону',
    'Волгоград', 'Воронеж', 'Красноярск', 'Омск', 'Иркутск', 'Владивосток',
    'Подольск', 'Химки', 'Балашиха', 'Мытищи', 'Красногорск', 'Одинцово',
    'Тула', 'Новомосковск', 'Тверь', 'Ярославль', 'Рязань', 'Калуга',
    'Владимир', 'Белгород', 'Курск', 'Липецк', 'Тамбов', 'Брянск',
    'Калининград', 'Мурманск', 'Архангельск', 'Вологда', 'Череповец',
    'Стерлитамак', 'Салават', 'Ижевск', 'Чебоксары', 'Йошкар-Ола',
    'Оренбург', 'Пенза', 'Ульяновск', 'Киров', 'Магнитогорск',
    'Сургут', 'Нижневартовск', 'Новый Уренгой', 'Кемерово', 'Новокузнецк',
    'Томск', 'Барнаул', 'Бийск', 'Хабаровск', 'Владивосток',
    'Новороссийск', 'Армавир', 'Анапа', 'Геленджик', 'Ставрополь',
    'Махачкала', 'Грозный', 'Владикавказ'
  ],
  region: [
    'Татарстан', 'Республика Татарстан', 'Москва', 'Московская область',
    'Санкт-Петербург', 'Ленинградская область', 'Свердловская область',
    'Новосибирская область', 'Краснодарский край', 'Нижегородская область',
    'Самарская область', 'Башкортостан', 'Пермский край', 'Саратовская область',
    'Челябинская область', 'Тюменская область', 'Ростовская область',
    'Волгоградская область', 'Красноярский край', 'Тульская область',
    'Тверская область', 'Ярославская область', 'Рязанская область',
    'Калужская область', 'Владимирская область', 'Воронежская область',
    'Белгородская область', 'Курская область', 'Липецкая область',
    'Тамбовская область', 'Брянская область', 'Калининградская область',
    'Мурманская область', 'Архангельская область', 'Вологодская область',
    'Удмуртская', 'Чувашская', 'Оренбургская область', 'Пензенская область',
    'Ульяновская область', 'Кировская область', 'Кемеровская область',
    'Томская область', 'Алтайский край', 'Приморский край', 'Хабаровский край',
    'Ставропольский край'
  ]
};
const GEO_QUICK = {
  city: ['Казань', 'Самара', 'Москва', 'Санкт-Петербург', 'Екатеринбург', 'Новосибирск'],
  region: ['Татарстан', 'Московская область', 'Самарская область', 'Краснодарский край', 'Свердловская область', 'Приволжский ФО']
};
const geoState = {
  scope: 'city',
  city: ['Казань'],
  region: []
};

async function api(url, options = {}) {
  const response = await fetch(url, options);
  if (!response.ok) throw Error(await response.text());
  return response.json();
}

async function providers() {
  try {
    const p = await api('/api/providers');
    $('#providers').textContent = p.demo_mode
      ? '● DEMO • моки'
      : `● V5 LIVE • ${p.object || ''} • owner ${p.owner || ''}`;
  } catch {
    $('#providers').textContent = 'Источники недоступны';
  }
}

function initDirections() {
  const box = $('#directions');
  box.innerHTML = BUILDING_TYPES.map((x, i) => `<button type="button" class="chip ${i === 0 ? 'active' : ''}" data-query="${esc(x)}">${esc(x)}</button>`).join('');
  box.addEventListener('click', event => {
    const btn = event.target.closest('button[data-query]');
    if (!btn) return;
    const activeCount = box.querySelectorAll('button.active').length;
    if (btn.classList.contains('active') && activeCount === 1) return;
    btn.classList.toggle('active');
  });
}

function selectedBuildingTypes() {
  return [...$('#directions').querySelectorAll('button.active')]
    .map(btn => btn.dataset.query)
    .filter(Boolean);
}

function setScope(scope) {
  geoState.scope = scope;
  $('#scopeTabs').querySelectorAll('button').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.scope === scope);
  });
  $('#geoPicker').style.display = scope === 'country' ? 'none' : '';
  $('#geoLabel').textContent = scope === 'region' ? 'Регионы' : 'Города';
  $('#geoSearch').placeholder = scope === 'region' ? 'Татарстан, Самарская область…' : 'Казань, Самара…';
  $('#geoSearch').value = '';
  renderGeoTags();
  renderGeoSuggest();
  renderGeoQuick();
}

function addGeo(value) {
  const scope = geoState.scope;
  if (scope === 'country') return;
  const clean = (value || '').trim();
  if (!clean) return;
  const list = geoState[scope];
  if (!list.some(x => x.toLowerCase() === clean.toLowerCase())) {
    list.push(clean);
  }
  $('#geoSearch').value = '';
  renderGeoTags();
  renderGeoSuggest();
  renderGeoQuick();
}

function removeGeo(scope, value) {
  geoState[scope] = geoState[scope].filter(x => x !== value);
  renderGeoTags();
  renderGeoSuggest();
  renderGeoQuick();
}

function toggleGeo(value) {
  const scope = geoState.scope;
  if (scope === 'country') return;
  const clean = (value || '').trim();
  if (!clean) return;
  if (geoState[scope].some(x => x.toLowerCase() === clean.toLowerCase())) {
    removeGeo(scope, geoState[scope].find(x => x.toLowerCase() === clean.toLowerCase()) || clean);
    return;
  }
  addGeo(clean);
}

function renderGeoTags() {
  const box = $('#geoTags');
  if (geoState.scope === 'country') {
    box.innerHTML = '<span class="geo-tag fixed">Вся Россия</span>';
    return;
  }
  const list = geoState.scope === 'region' ? geoState.region : geoState.city;
  box.innerHTML = list.length
    ? list.map(x => `<span class="geo-tag">${esc(geoState.scope === 'region' ? 'рег. ' : '')}${esc(x)}<button type="button" data-remove-geo="${esc(x)}">×</button></span>`).join('')
    : '<span class="geo-empty">Ничего не выбрано</span>';
}

function renderGeoSuggest() {
  const box = $('#geoSuggest');
  const scope = geoState.scope;
  if (scope === 'country') {
    box.innerHTML = '';
    return;
  }
  const q = $('#geoSearch').value.trim().toLowerCase();
  if (!q) {
    box.innerHTML = '';
    return;
  }
  const selected = new Set(geoState[scope].map(x => x.toLowerCase()));
  const rows = GEO[scope]
    .filter(x => !selected.has(x.toLowerCase()))
    .filter(x => !q || x.toLowerCase().includes(q))
    .slice(0, 8);
  box.innerHTML = rows.map(x => `<button type="button" data-add-geo="${esc(x)}">${esc(x)}<span>${scope === 'region' ? 'регион' : 'город'}</span></button>`).join('');
}

function renderGeoQuick() {
  const box = $('#geoQuick');
  if (geoState.scope === 'country') {
    box.innerHTML = '<span>Поиск пойдёт по всей России через набор крупных городов.</span>';
    return;
  }
  const selected = new Set(geoState[geoState.scope].map(x => x.toLowerCase()));
  box.innerHTML = GEO_QUICK[geoState.scope]
    .map(x => `<button type="button" class="quick-chip ${selected.has(x.toLowerCase()) ? 'active' : ''}" data-toggle-geo="${esc(x)}">${esc(x)}</button>`)
    .join('');
}

function initGeo() {
  $('#scopeTabs').addEventListener('click', event => {
    const btn = event.target.closest('button[data-scope]');
    if (!btn) return;
    setScope(btn.dataset.scope);
  });
  $('#geoSearch').addEventListener('input', renderGeoSuggest);
  $('#geoSearch').addEventListener('keydown', event => {
    if (event.key !== 'Enter') return;
    const first = $('#geoSuggest button[data-add-geo]');
    event.preventDefault();
    addGeo(first?.dataset.addGeo || $('#geoSearch').value);
  });
  $('#geoSuggest').addEventListener('click', event => {
    const btn = event.target.closest('button[data-add-geo]');
    if (!btn) return;
    addGeo(btn.dataset.addGeo);
  });
  $('#geoQuick').addEventListener('click', event => {
    const btn = event.target.closest('button[data-toggle-geo]');
    if (!btn) return;
    if (btn.dataset.toggleGeo === 'Приволжский ФО') {
      const regions = ['Татарстан', 'Башкортостан', 'Самарская область', 'Нижегородская область', 'Пермский край', 'Саратовская область'];
      const allSelected = regions.every(x => geoState.region.some(r => r.toLowerCase() === x.toLowerCase()));
      regions.forEach(x => allSelected ? removeGeo('region', x) : addGeo(x));
      return;
    }
    toggleGeo(btn.dataset.toggleGeo);
  });
  $('#geoTags').addEventListener('click', event => {
    const btn = event.target.closest('button[data-remove-geo]');
    if (!btn) return;
    removeGeo(geoState.scope, btn.dataset.removeGeo);
  });
  setScope('city');
}

function initCount() {
  const input = $('#count');
  const output = $('#countValue');
  const set = value => {
    const next = Math.max(Number(input.min), Math.min(Number(input.max), Number(value) || 1));
    input.value = String(next);
    output.textContent = String(next);
    input.style.setProperty('--value', `${((next - Number(input.min)) / (Number(input.max) - Number(input.min))) * 100}%`);
  };
  input.addEventListener('input', () => set(input.value));
  $('#countMinus').addEventListener('click', () => set(Number(input.value) - 1));
  $('#countPlus').addEventListener('click', () => set(Number(input.value) + 1));
  set(input.value);
}

function verify(v) {
  if (!v) return '';
  const checks = (v.checks || []).map(c => `<div class="verify-check ${c.passed ? 'ok' : 'fail'}"><span class="verify-dot">${c.passed ? '✓' : '×'}</span><div><b>${esc(c.label)}</b><small>${esc(c.detail)}</small></div></div>`).join('');
  const title = v.status === 'verified' ? 'Объект подтвержден' : v.status === 'probable' ? 'Вероятное совпадение' : 'Нужна проверка';
  return `<div class="verify-box ${esc(v.status)}"><div class="verify-head"><div><small>ПРОВЕРКА ОБЪЕКТА</small><strong>${title}</strong></div><div class="verify-score">${v.score}%</div></div><div class="verify-grid">${checks}</div></div>`;
}

function contacts(people) {
  if (!people.length) {
    return '<div class="empty-inline">Персональные контакты не подтверждены. Общие телефоны компании сюда не подставляются.</div>';
  }
  return people.map(p => `<div class="person actionable">
    <b>${esc(p.full_name)}</b>
    <div class="role">${esc(role(p.role))}</div>
    <div class="contacts">${(p.contacts || []).map(c => `<span class="contact">${esc(c.type)}: ${esc(c.value)} · ${esc(contactScope(c))} · ${esc(c.confidence)}% ${link(c.source_url, 'источник')}</span>`).join('')}</div>
    <div class="source">${link(p.source, 'профиль ЛПР')}</div>
  </div>`).join('');
}

function candidates(people) {
  if (!people.length) return '<div class="empty-inline">Владелец/ЛПР пока не установлен.</div>';
  return people.map(p => `<div class="person">
    ${p.effective_share != null ? `<span class="share">${esc(p.effective_share)}%</span>` : ''}
    <b>${esc(p.full_name)}</b>
    <div class="role">${esc(role(p.role))}</div>
    <div class="source">${link(p.source, 'источник роли')}</div>
  </div>`).join('');
}

function contactResearch(links) {
  if (!links?.length) return '';
  return `<div class="owner-links">${links.map(x => `<a class="action-link" href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.label)}</a>`).join('')}</div>`;
}

function objectContacts(items) {
  if (!items?.length) return '';
  return `<div class="fallback-contacts">${items.map(c => `<span class="contact">${esc(c.type)}: ${esc(c.value)} · ${esc(c.label || contactScope(c))} ${link(c.source_url, 'источник')}</span>`).join('')}</div>`;
}

function financeBlock(c, finance) {
  const f = finance || c?.finance || {};
  if (!c) {
    return '<div class="empty-inline">Финансовые данные появятся после подтверждения ИНН.</div>';
  }
  const links = (f.links || []).map(x => `<a class="action-link" href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.label)}</a>`).join('');
  return `<div class="sub">Выручка ${money(f.revenue ?? c.revenue)} · прибыль ${money(f.profit ?? c.profit)} · сотрудники ${f.employees ?? c.employees ?? '-'}</div>
    ${f.period ? `<div class="sub">Период: ${esc(f.period)}</div>` : ''}
    <div class="empty-inline">${esc(f.summary || 'Финансовые данные проверяются по открытым источникам.')}</div>
    <div class="source">Источник: ${link(f.source || c.source, 'провайдер компании')}</div>
    <div class="owner-links">${links}</div>`;
}

function cadastreBlock(o) {
  if (o.cadastral_number) {
    return `<div class="sub">Кадастр: ${esc(o.cadastral_number)} · площадь ${o.cadastral_area ? Math.round(o.cadastral_area).toLocaleString('ru-RU') + ' м²' : '-'}</div>
      <div class="source">${link(o.cadastre_source, 'источник кадастра')}</div>`;
  }
  return '<div class="empty-inline">Кадастровый номер не подтверждён бесплатными источниками. Карточка оставлена как объект с карты, без утверждения правообладателя по кадастру.</div>';
}

function render(rows) {
  rows = [...rows].sort((a, b) => {
    const rank = {
      ready_owner_contact: 6,
      ready_owner_only: 5,
      needs_photo: 4,
      needs_owner: 3,
      needs_object_enrichment: 2,
      rejected: 1,
      ready: 6,
      needs_cadastre: 4,
      needs_enrichment: 2,
      reject_candidate: 1
    };
    return (rank[b.lead_quality?.status] || 0) - (rank[a.lead_quality?.status] || 0);
  });
  $('#countOut').textContent = rows.length;
  $('#results').innerHTML = rows.length ? rows.map(r => {
    const o = r.object || {};
    const c = r.company;
    const light = r.lighting || {};
    const people = r.people || [];
    const finance = r.finance || c?.finance;
    const peopleCandidates = r.people_candidates || [];
    const researchLinks = r.contact_research || [];
    const objectContactRows = r.object_contacts || [];
    const ownerResearch = r.owner_research || [];
    const ownerLinks = ownerResearch.map(x => `<a class="action-link" href="${esc(x.url)}" target="_blank" rel="noreferrer">${esc(x.label)}</a>`).join('');
    const quality = r.lead_quality || {};
    const qualityItems = [...(quality.reasons || []), ...(quality.warnings || [])]
      .map(x => `<div class="quality-item">${esc(x)}</div>`).join('');
    return `<article>
      <div class="object-photo">
        ${o.photo_url ? `<img src="${esc(o.photo_url)}" alt="${esc(o.name)}">` : `<div class="photo-missing"><span>НУЖНО ФОТО</span><small>Карточка сохранена, фото проверяется по картам/поиску</small></div>`}
        <div class="photo-overlay"><span>${esc(o.source_provider || 'OBJECT')}</span><strong>${esc(light.status || 'low').toUpperCase()} · ${light.score || 0}% LIGHT</strong></div>
      </div>
      <div class="top">
        <div><small>КОММЕРЧЕСКОЕ ЗДАНИЕ</small><h3>${esc(o.name)}</h3><div class="addr">${esc(o.address)}</div></div>
        <span class="badge ${esc(quality.status || '')}">${esc(quality.label || r.relation_status)}</span>
      </div>
      <div class="actions">
        ${o.source_url ? `<a class="action-link" href="${esc(o.source_url)}" target="_blank" rel="noreferrer">Источник объекта</a>` : ''}
        ${o.map_url ? `<a class="action-link" href="${esc(o.map_url)}" target="_blank" rel="noreferrer">Карта / панорама</a>` : ''}
        <button class="secondary" type="button" data-proposal="${o.id}">КП</button>
      </div>
      <div class="metrics">
        <div class="metric"><small>ПОДСВЕТКА</small><b>${light.score || 0}%</b></div>
        <div class="metric"><small>КАДАСТР</small><b>${esc(o.cadastral_number || '-')}</b></div>
        <div class="metric"><small>ПЛОЩАДЬ</small><b>${o.cadastral_area ? Math.round(o.cadastral_area).toLocaleString('ru-RU') + ' м²' : '-'}</b></div>
      </div>
      <div class="section"><small>ОБЩАЯ ИНФОРМАЦИЯ О ЗДАНИИ</small><div class="sub">Категория: ${esc(o.category || '-')} · проверка ${r.verification?.score || 0}% · confidence ${r.confidence}%</div>${cadastreBlock(o)}<div class="sub">Кадастровая стоимость: ${money(o.cadastral_value)}</div></div>
      <div class="section quality ${esc(quality.status || '')}"><small>СТАТУС ЛИДА</small><b>${esc(quality.label || 'Проверяется')}</b>${qualityItems || '<div class="sub">Критичные условия закрыты.</div>'}</div>
      <div class="section"><small>ВЛАДЕЛЕЦ / ЮРЛИЦО</small>${c ? `<b>${esc(c.name)}</b><div class="sub">ИНН ${esc(c.inn)} · ОГРН ${esc(c.ogrn || '-')} · статус ${esc(c.status || '-')}</div><div class="source">${link(c.source, 'источник компании')}</div>` : `<div class="empty-inline">Правообладатель пока не подтвержден.</div><div class="owner-links">${ownerLinks}</div>`}</div>
      <div class="section"><small>ФИНАНСЫ</small>${financeBlock(c, finance)}</div>
      <div class="section"><small>ВЛАДЕЛЬЦЫ И ЛПР</small>${candidates(peopleCandidates)}</div>
      <div class="section"><small>КОМУ ПИСАТЬ / КОНТАКТЫ</small>${contacts(people)}${objectContacts(objectContactRows)}${contactResearch(researchLinks)}</div>
      <div class="section"><small>ПРИГОДНОСТЬ ДЛЯ ПОДСВЕТКИ</small><div class="sub">${(light.reasons || []).map(esc).join(' · ') || 'Не хватает фото/панорамы фасада'}</div></div>
      <div class="section">${verify(r.verification)}</div>
      <div class="section proposal" id="proposal-${o.id}"></div>
    </article>`;
  }).join('') : '<div class="empty">Карточек пока нет</div>';
}

async function poll(id) {
  $('#status').classList.remove('hide');
  for (;;) {
    const h = await api(`/api/hunts/${id}`);
    $('#statusText').textContent = h.message;
    $('#percent').textContent = h.progress + '%';
    $('#bar').style.width = h.progress + '%';
    if (['completed', 'failed'].includes(h.status)) {
      render(await api(`/api/hunts/${id}/results`));
      return;
    }
    await new Promise(resolve => setTimeout(resolve, 500));
  }
}

document.addEventListener('click', async event => {
  const btn = event.target.closest('button[data-proposal]');
  if (!btn) return;
  const id = btn.dataset.proposal;
  const box = $(`#proposal-${id}`);
  box.innerHTML = '<small>КП</small><div class="sub">Генерация предложения...</div>';
  try {
    const p = await api(`/api/objects/${id}/proposal`, {method: 'POST'});
    box.innerHTML = `<small>КП / ФАСАД</small><div class="proposal-text">${esc(p.facade_analysis || p.analysis || 'Модель не настроена.')}</div><div class="proposal-text">${esc(p.lighting_idea || '')}</div><div class="proposal-text">${esc(p.proposal || '')}</div>`;
  } catch (e) {
    box.innerHTML = `<small>КП</small><div class="empty-inline">Не удалось создать КП: ${esc(e.message)}</div>`;
  }
});

$('#form').onsubmit = async event => {
  event.preventDefault();
  $('#results').innerHTML = '<div class="empty">Идет поиск здания, владельца и контактов...</div>';
  const scope = geoState.scope;
  const typedGeo = $('#geoSearch').value.trim();
  if (typedGeo && scope !== 'country') addGeo(typedGeo);
  const selected = scope === 'region' ? geoState.region : geoState.city;
  const city = scope === 'country' ? 'Россия' : selected.join(', ');
  const selectedTypes = selectedBuildingTypes();
  const query = selectedTypes.join(', ');
  if (!selectedTypes.length) {
    $('#results').innerHTML = '<div class="empty">Выберите хотя бы один тип здания</div>';
    return;
  }
  if (!city.trim()) {
    $('#results').innerHTML = '<div class="empty">Выберите город или регион</div>';
    return;
  }
  const hunt = await api('/api/hunts', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({city, query, count: Number($('#count').value)})
  });
  poll(hunt.id);
};

initDirections();
initGeo();
initCount();
providers();
