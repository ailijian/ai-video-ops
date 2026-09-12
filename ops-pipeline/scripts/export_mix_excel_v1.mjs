import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";


const require = createRequire(import.meta.url);
const { FileBlob, SpreadsheetFile } = require("@oai/artifact-tool");

const EXPORTER_VERSION = "export_mix_excel_v1.mjs@1.0";
const EXPECTED_HEADERS = ["视频制作标题", "视频制作口播内容"];


function parseArgs(argv) {
  const result = {};
  for (let index = 0; index < argv.length; index += 2) {
    const key = argv[index];
    const value = argv[index + 1];
    if (!key?.startsWith("--") || value === undefined) {
      throw new Error(`Invalid argument sequence near ${key ?? "<end>"}.`);
    }
    result[key.slice(2)] = value;
  }
  if (!result.template || !result.preview || !result["validation-output"]) {
    throw new Error("--template, --preview and --validation-output are required.");
  }
  const mode = result.mode ?? "export";
  if (mode === "export") {
    for (const required of ["batch", "output", "receipt"]) {
      if (!result[required]) throw new Error(`Missing required argument --${required}.`);
    }
  }
  return result;
}


async function sha256File(filePath) {
  return crypto.createHash("sha256").update(await fs.readFile(filePath)).digest("hex");
}


async function fileExists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}


function listSheetNames(workbook) {
  const names = [];
  for (let index = 0; index < 100; index += 1) {
    try {
      const sheet = workbook.worksheets.getItemAt(index);
      if (!sheet) break;
      names.push(sheet.name);
    } catch {
      break;
    }
  }
  return names;
}


function validateApprovedBatch(batch) {
  if (batch.schema_version !== "approved-generation-batch-v1.0") {
    throw new Error("Mix Excel Export requires an Approved Generation Batch.");
  }
  if (batch.status !== "approved" || batch.profile !== "mix") {
    throw new Error("Mix Excel Export requires an Approved Mix Batch.");
  }
  if (batch.human_review?.all_export_items_human_approved !== true) {
    throw new Error("All Mix export Items must be Human Approved.");
  }
  const contents = batch.contents ?? [];
  if (contents.length !== 4 || contents.some((item) => item.status !== "human_approved")) {
    throw new Error("Post-Replenishment Mix Export requires four Human-approved Items.");
  }
  return contents.map((item) => [String(item.title ?? ""), String(item.narration ?? "")]);
}


const args = parseArgs(process.argv.slice(2));
const mode = args.mode ?? "export";
if (!new Set(["inspect-template", "export", "validate-existing"]).has(mode)) {
  throw new Error("Unsupported Mix Excel exporter mode.");
}
const templatePath = path.resolve(args.template);
const previewPath = path.resolve(args.preview);
const validationPath = path.resolve(args["validation-output"]);
const templateShaBefore = await sha256File(templatePath);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sheetNames = listSheetNames(workbook);
if (JSON.stringify(sheetNames) !== JSON.stringify(["Sheet1"])) {
  throw new Error("Mix Template sheet contract changed.");
}
const sheet = workbook.worksheets.getItem("Sheet1");
const sourceRowsOneToFour = sheet.getRange("A1:B4").values;
const sourceFormulasOneToFour = sheet.getRange("A1:B4").formulas;
const headers = sheet.getRange("A4:B4").values?.[0] ?? [];
if (JSON.stringify(headers) !== JSON.stringify(EXPECTED_HEADERS)) {
  throw new Error("Mix Template row 4 headers changed.");
}

if (mode === "inspect-template") {
  await fs.mkdir(path.dirname(previewPath), { recursive: true });
  const preview = await workbook.render({
    sheetName: "Sheet1",
    range: "A1:B10",
    scale: 2,
    format: "png",
  });
  await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
  const result = {
    schema_version: "mix-excel-template-inspection-v1.0",
    template_path: templatePath,
    template_sha256: templateShaBefore,
    sheet_names: sheetNames,
    row_4_headers: headers,
    rows_1_4: sourceRowsOneToFour,
    preview_path: previewPath,
    passed: true,
  };
  await fs.mkdir(path.dirname(validationPath), { recursive: true });
  await fs.writeFile(validationPath, JSON.stringify(result, null, 2), "utf8");
  console.log(JSON.stringify(result));
  process.exit(0);
}

const batchPath = path.resolve(args.batch);
const outputPath = path.resolve(args.output);
const receiptPath = path.resolve(args.receipt);
if (templatePath === outputPath) throw new Error("Mix output cannot overwrite the Template.");
if (mode === "export" && (await fileExists(outputPath))) {
  throw new Error("Mix Excel output already exists and cannot be overwritten.");
}
if (mode === "validate-existing" && !(await fileExists(outputPath))) {
  throw new Error("Existing Mix Excel output is required for validation.");
}
const batch = JSON.parse(await fs.readFile(batchPath, "utf8"));
const rows = validateApprovedBatch(batch);
if (mode === "export") {
  sheet.getRange("A5:B100").clear({ applyTo: "contents" });
  for (let rowIndex = 6; rowIndex <= 8; rowIndex += 1) {
    sheet.getRange(`A${rowIndex}:B${rowIndex}`).copyFrom(sheet.getRange("A5:B5"), "all");
  }
  sheet.getRange("A5:B8").values = rows;
  sheet.getRange("A5:B8").format.wrapText = true;
  sheet.getRange("A5:B8").format.verticalAlignment = "center";
  sheet.getRange("A5:B8").format.rowHeight = 88;
  workbook.recalculate();
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
}

const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const reopenedSheetNames = listSheetNames(reopened);
const reopenedSheet = reopened.worksheets.getItem("Sheet1");
const reopenedRowsOneToFour = reopenedSheet.getRange("A1:B4").values;
const reopenedFormulasOneToFour = reopenedSheet.getRange("A1:B4").formulas;
const reopenedHeaders = reopenedSheet.getRange("A4:B4").values?.[0] ?? [];
const reopenedRows = reopenedSheet.getRange("A5:B8").values;
const internalMetadataRange = reopenedSheet.getRange("C5:Z8").values;
const reopenedValues = reopenedSheet.getRange("A1:B8").values;
const inspected = await reopened.inspect({
  kind: "table",
  sheetId: "Sheet1",
  range: "A1:B8",
  include: "values,formulas",
  tableMaxRows: 8,
  tableMaxCols: 2,
  maxChars: 5000,
});
const errors = await reopened.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!",
  options: { useRegex: true, maxResults: 100 },
  summary: "final Mix export formula error scan",
});
const formulaErrorCount = reopenedValues
  .flat()
  .filter((value) => /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A|#NUM!|#NULL!|#SPILL!|#CALC!/.test(String(value ?? "")))
  .length;
await fs.mkdir(path.dirname(previewPath), { recursive: true });
const preview = await reopened.render({
  sheetName: "Sheet1",
  range: "A1:B10",
  scale: 2,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const templateShaAfter = await sha256File(templatePath);
const exportedAt = new Date().toISOString();
const validations = {
  workbook_reopened: true,
  sheets_match_template: JSON.stringify(reopenedSheetNames) === JSON.stringify(sheetNames),
  rows_1_4_values_preserved: JSON.stringify(reopenedRowsOneToFour) === JSON.stringify(sourceRowsOneToFour),
  rows_1_4_formulas_preserved: JSON.stringify(reopenedFormulasOneToFour) === JSON.stringify(sourceFormulasOneToFour),
  row_4_headers_exact: JSON.stringify(reopenedHeaders) === JSON.stringify(EXPECTED_HEADERS),
  four_rows_exact: JSON.stringify(reopenedRows) === JSON.stringify(rows),
  internal_metadata_absent: internalMetadataRange.flat().every((value) => value == null || value === ""),
  source_template_unchanged: templateShaBefore === templateShaAfter,
  formula_errors_absent: formulaErrorCount === 0,
};
const validation = {
  schema_version: "mix-excel-artifact-tool-validation-v1.0",
  exporter_version: EXPORTER_VERSION,
  mode,
  exported_at: exportedAt,
  batch_path: batchPath,
  batch_sha256: await sha256File(batchPath),
  template_path: templatePath,
  template_sha256_before: templateShaBefore,
  template_sha256_after: templateShaAfter,
  output_path: outputPath,
  output_sha256: await sha256File(outputPath),
  preview_path: previewPath,
  sheet_names: reopenedSheetNames,
  row_4_headers: reopenedHeaders,
  exported_row_count: rows.length,
  inspected_range: "Sheet1!A1:B8",
  inspect_recorded: Boolean(inspected.ndjson),
  formula_error_scan_recorded: Boolean(errors.ndjson),
  formula_error_count: formulaErrorCount,
  validations,
};
validation.passed = Object.values(validations).every(Boolean);
if (!validation.passed) {
  throw new Error(`Mix Excel artifact-tool validation failed: ${JSON.stringify(validation)}`);
}
const receipt = {
  schema_version: "mix-excel-export-receipt-v1.0",
  exporter_version: EXPORTER_VERSION,
  exported_at: exportedAt,
  batch_path: batchPath,
  batch_sha256: validation.batch_sha256,
  template_path: templatePath,
  template_sha256: templateShaBefore,
  output_path: outputPath,
  output_sha256: validation.output_sha256,
  exported_row_count: rows.length,
  row_4_headers: EXPECTED_HEADERS,
  first_data_row: 5,
  internal_metadata_columns_added: false,
  source_template_modified: false,
  validation_passed: true,
};
await fs.mkdir(path.dirname(validationPath), { recursive: true });
await fs.writeFile(validationPath, JSON.stringify(validation, null, 2), "utf8");
await fs.writeFile(receiptPath, JSON.stringify(receipt, null, 2), "utf8");
console.log(JSON.stringify(validation));
