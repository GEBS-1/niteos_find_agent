import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const repoRoot = path.resolve(".");
const dataDir = path.join(repoRoot, "data");

function styleHeader(range) {
  range.format = {
    fill: "#111827",
    font: { bold: true, color: "#FFFFFF" },
  };
}

async function exportWorkbook(workbook, fileName) {
  await fs.mkdir(dataDir, { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(path.join(dataDir, fileName));
}

async function buildProducts() {
  const workbook = Workbook.create();
  const catalog = workbook.worksheets.add("Catalog");
  const rules = workbook.worksheets.add("Lighting Rules");
  const notes = workbook.worksheets.add("Notes");

  catalog.showGridLines = false;
  catalog.getRange("A1:I1").values = [[
    "SKU",
    "Product name",
    "Category",
    "Use case",
    "Power W",
    "Luminous flux lm",
    "Unit price RUB",
    "Demo",
    "Comment",
  ]];
  catalog.getRange("A2:I7").values = [
    ["NTS-FACADE-36-DEMO", "NITEOS Facade Line 36", "Architectural", "Facade accent", 36, 4200, 18500, true, "Демонстрационная цена"],
    ["NTS-FACADE-72-DEMO", "NITEOS Facade Line 72", "Architectural", "Large facade wash", 72, 8900, 31500, true, "Демонстрационная цена"],
    ["NTS-FLOOD-100-DEMO", "NITEOS Flood 100", "Industrial", "Yard lighting", 100, 13500, 22400, true, "Демонстрационная цена"],
    ["NTS-FLOOD-180-DEMO", "NITEOS Flood 180", "Industrial", "Loading area", 180, 25200, 38900, true, "Демонстрационная цена"],
    ["NTS-STREET-80-DEMO", "NITEOS Street 80", "Street", "Driveway and perimeter", 80, 11200, 19800, true, "Демонстрационная цена"],
    ["NTS-CONTROL-DEMO", "NITEOS Control Box", "Control", "Lighting control cabinet", 0, 0, 47000, true, "Демонстрационная цена"],
  ];
  styleHeader(catalog.getRange("A1:I1"));
  catalog.getRange("E2:G7").format.numberFormat = "#,##0";
  catalog.getRange("A1:I7").format.borders = { preset: "inside", style: "thin", color: "#CBD5E1" };
  catalog.getRange("A:I").format.autofitColumns();
  catalog.freezePanes.freezeRows(1);
  catalog.tables.add("A1:I7", true, "ProductCatalogDemo");

  rules.showGridLines = false;
  rules.getRange("A1:F1").values = [["Object type", "Scenario", "Rule", "Base product", "Formula hint", "Demo"]];
  rules.getRange("A2:F6").values = [
    ["Логистический комплекс", "Фасад", "1 линейный светильник на 6-8 м фасада", "NTS-FACADE-72-DEMO", "ceil(facade_width_m / 7)", true],
    ["Логистический комплекс", "Погрузочные ворота", "1 прожектор на 1-2 ворот", "NTS-FLOOD-100-DEMO", "ceil(gates_count / 2)", true],
    ["Промышленный двор", "Проезд", "1 опора/светильник на 18-22 м периметра", "NTS-STREET-80-DEMO", "ceil(perimeter_m / 20)", true],
    ["Складская зона", "Территория", "1 прожектор на 450-650 м2", "NTS-FLOOD-180-DEMO", "ceil(yard_area_m2 / 550)", true],
    ["Любой объект", "Управление", "1 шкаф на проект", "NTS-CONTROL-DEMO", "1", true],
  ];
  styleHeader(rules.getRange("A1:F1"));
  rules.getRange("A1:F6").format.borders = { preset: "inside", style: "thin", color: "#CBD5E1" };
  rules.getRange("A:F").format.autofitColumns();
  rules.freezePanes.freezeRows(1);

  notes.showGridLines = false;
  notes.getRange("A1:B5").values = [
    ["Field", "Value"],
    ["Purpose", "Демонстрационный каталог продукции и цен для MVP NITEOS Hunt"],
    ["Important", "Все цены и характеристики являются тестовыми"],
    ["Replace with", "Официальный прайс, реальные SKU, фотометрия, гарантийные условия"],
    ["Spec", "NITEOS_HUNT_PRODUCT_SPEC.md"],
  ];
  styleHeader(notes.getRange("A1:B1"));
  notes.getRange("A:B").format.autofitColumns();

  await exportWorkbook(workbook, "products.xlsx");
}

async function buildTargetClients() {
  const workbook = Workbook.create();
  const clients = workbook.worksheets.add("Target Clients");
  const scoring = workbook.worksheets.add("Scoring");

  clients.showGridLines = false;
  clients.getRange("A1:K1").values = [[
    "Segment",
    "Region",
    "City",
    "Company profile",
    "Revenue from RUB",
    "Preferred object",
    "Must have photo",
    "Priority role",
    "Pain point",
    "Demo",
    "Notes",
  ]];
  clients.getRange("A2:K6").values = [
    ["Складская логистика", "Республика Татарстан", "Казань", "Собственный складской комплекс", 100000000, "Логистический комплекс", true, "Технический директор", "Фасад и ворота плохо видны ночью", true, "Приоритетный сценарий MVP"],
    ["Производство", "Республика Татарстан", "Набережные Челны", "Производственная площадка", 150000000, "Промышленный объект", true, "Главный энергетик", "Освещение территории и безопасность", true, "Подходит для промышленного освещения"],
    ["Оптовая торговля", "Республика Татарстан", "Альметьевск", "Складской корпус с проездом", 80000000, "Складской корпус", true, "Директор по эксплуатации", "Нужна подсветка фасада и въезда", true, "Ниже идеального порога, но полезно для теста"],
    ["Девелопмент", "Приволжский ФО", "Любой", "Торговый или деловой объект", 200000000, "Коммерческое здание", true, "Управляющий объектом", "Имиджевая подсветка", true, "Расширение после MVP"],
    ["Муниципальные объекты", "Приволжский ФО", "Любой", "Спортивный или общественный объект", 50000000, "Общественное здание", true, "Ответственный за закупки", "Благоустройство и безопасность", true, "Нужна отдельная логика закупок"],
  ];
  styleHeader(clients.getRange("A1:K1"));
  clients.getRange("E2:E6").format.numberFormat = "#,##0";
  clients.getRange("A1:K6").format.borders = { preset: "inside", style: "thin", color: "#CBD5E1" };
  clients.getRange("A:K").format.autofitColumns();
  clients.freezePanes.freezeRows(1);
  clients.tables.add("A1:K6", true, "TargetClientsDemo");

  scoring.showGridLines = false;
  scoring.getRange("A1:D1").values = [["Criterion", "Weight", "Positive signal", "Negative signal"]];
  scoring.getRange("A2:D8").values = [
    ["Действующая компания", 20, "Статус действующая", "Ликвидация или недостоверность"],
    ["Выручка", 15, "От 100 млн рублей", "Нет данных или низкая выручка"],
    ["Подходящий объект", 20, "Склад, производство, коммерческое здание", "Нет собственного объекта"],
    ["Фотографии", 15, "Есть фасад или территория", "Нет фото"],
    ["Контакты", 15, "Есть сайт/email/телефон", "Контакты не найдены"],
    ["ЛПР", 10, "Найден технический руководитель", "Нет понятного адресата"],
    ["География", 5, "В целевом регионе", "Вне региона"],
  ];
  styleHeader(scoring.getRange("A1:D1"));
  scoring.getRange("B2:B8").format.numberFormat = "0";
  scoring.getRange("A1:D8").format.borders = { preset: "inside", style: "thin", color: "#CBD5E1" };
  scoring.getRange("A:D").format.autofitColumns();
  scoring.freezePanes.freezeRows(1);

  await exportWorkbook(workbook, "target-clients.xlsx");
}

await buildProducts();
await buildTargetClients();
