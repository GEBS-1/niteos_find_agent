import { FileBlob, SpreadsheetFile } from "@oai/artifact-tool";

const checks = [
  {
    path: "data/products.xlsx",
    sheets: ["Catalog", "Lighting Rules", "Notes"],
  },
  {
    path: "data/target-clients.xlsx",
    sheets: ["Target Clients", "Scoring"],
  },
];

for (const check of checks) {
  const input = await FileBlob.load(check.path);
  const workbook = await SpreadsheetFile.importXlsx(input);

  const summary = await workbook.inspect({
    kind: "workbook,sheet,table",
    maxChars: 2500,
    tableMaxRows: 3,
    tableMaxCols: 6,
  });
  console.log(`\n${check.path}`);
  console.log(summary.ndjson);

  const errors = await workbook.inspect({
    kind: "match",
    searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
    options: { useRegex: true, maxResults: 300 },
    summary: "formula error scan",
    maxChars: 1000,
  });
  const realErrorMatches = errors.ndjson
    .split("\n")
    .filter((line) => line.trim())
    .filter((line) => !line.includes("Cell search matched 0 entries."));
  if (realErrorMatches.length > 0) {
    throw new Error(`Formula errors found in ${check.path}:\n${errors.ndjson}`);
  }

  for (const sheetName of check.sheets) {
    const preview = await workbook.render({
      sheetName,
      autoCrop: "all",
      scale: 1,
      format: "png",
    });
    const bytes = new Uint8Array(await preview.arrayBuffer());
    if (bytes.length < 1000) {
      throw new Error(`Rendered preview for ${check.path} / ${sheetName} is unexpectedly small`);
    }
    console.log(`Rendered ${sheetName}: ${bytes.length} bytes`);
  }
}
