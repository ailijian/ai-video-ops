import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { createRequire } from "node:module";


const require = createRequire(import.meta.url);
const { FileBlob, SpreadsheetFile } = require("@oai/artifact-tool");

const EXPORTER_VERSION = "export_news_excel_v1.mjs@1.0";
const EXPECTED_HEADERS = ["标题1", "标题2", "标题3", "标题4", "标题5", "标题6"];


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
  for (const required of ["approval", "template", "output", "preview", "validation-output"]) {
    if (!result[required]) {
      throw new Error(`Missing required argument --${required}.`);
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


function validateApproval(approval) {
  const review = approval.human_review ?? {};
  if (approval.schema_version !== "news-generation-human-review-approval-v1.0") {
    throw new Error("News Excel Export requires the canonical Human Approval schema.");
  }
  if (approval.status !== "approved_for_export" || review.decision !== "approved") {
    throw new Error("News Excel Export is blocked without final Human Approval.");
  }
  if (review.reviewer !== "李健" || review.human_gate !== true) {
    throw new Error("News Excel Export requires the recorded Human Review gate.");
  }
  if (
    approval.approval_scope !==
    "cross_profile_repurpose_presentation_not_novel_content"
  ) {
    throw new Error("News Excel Export approval scope is invalid.");
  }
  const reuse = approval.reuse_declaration ?? {};
  if (
    reuse.reuse_intent !== "cross_profile_repurpose" ||
    reuse.semantic_novelty !== false ||
    reuse.historical_content_reused !== true
  ) {
    throw new Error("Repurpose approval may not be exported as Novel Content.");
  }
  const mapping = approval.approved_export_slot_mapping ?? {};
  const slots = mapping.slots ?? [];
  if (mapping.export_slot_count !== 6 || slots.length !== 6) {
    throw new Error("News Excel Export requires exactly six Human-approved slots.");
  }
  const headers = slots.map((slot) => slot.header);
  if (JSON.stringify(headers) !== JSON.stringify(EXPECTED_HEADERS)) {
    throw new Error("Human-approved News slot headers do not match the frozen Excel contract.");
  }
  if (mapping.first_display_slot_price_offer_anchor_recoverable !== true) {
    throw new Error("First display slot does not preserve a recoverable Price / Offer anchor.");
  }
  return slots.map((slot) => String(slot.text ?? ""));
}


const args = parseArgs(process.argv.slice(2));
const approvalPath = path.resolve(args.approval);
const templatePath = path.resolve(args.template);
const outputPath = path.resolve(args.output);
const previewPath = path.resolve(args.preview);
const validationOutputPath = path.resolve(args["validation-output"]);
const mode = args.mode ?? "export";

if (templatePath === outputPath) {
  throw new Error("News Excel output must not overwrite the source Template.");
}
if (!new Set(["export", "validate-existing"]).has(mode)) {
  throw new Error("Unsupported News Excel exporter mode.");
}
if (mode === "export" && (await fileExists(outputPath))) {
  throw new Error("News Excel output already exists and cannot be overwritten.");
}
if (mode === "validate-existing" && !(await fileExists(outputPath))) {
  throw new Error("Existing News Excel output is required for validation mode.");
}

const approval = JSON.parse(await fs.readFile(approvalPath, "utf8"));
const slotTexts = validateApproval(approval);
const templateShaBefore = await sha256File(templatePath);
const workbook = await SpreadsheetFile.importXlsx(await FileBlob.load(templatePath));
const sourceSheetNames = listSheetNames(workbook);
if (JSON.stringify(sourceSheetNames) !== JSON.stringify(["Sheet1"])) {
  throw new Error("News Template sheet contract changed.");
}
const sheet = workbook.worksheets.getItem("Sheet1");
const sourceRowsOneToFour = sheet.getRange("A1:F4").values;
const sourceHeaders = sheet.getRange("A4:F4").values?.[0] ?? [];
if (JSON.stringify(sourceHeaders) !== JSON.stringify(EXPECTED_HEADERS)) {
  throw new Error("News Template row 4 headers changed.");
}

if (mode === "export") {
  sheet.getRange("A5:F5").values = [slotTexts];
  workbook.recalculate();
  await fs.mkdir(path.dirname(outputPath), { recursive: true });
  const output = await SpreadsheetFile.exportXlsx(workbook);
  await output.save(outputPath);
}

const reopened = await SpreadsheetFile.importXlsx(await FileBlob.load(outputPath));
const reopenedSheetNames = listSheetNames(reopened);
const reopenedSheet = reopened.worksheets.getItem("Sheet1");
const reopenedRowsOneToFour = reopenedSheet.getRange("A1:F4").values;
const reopenedHeaders = reopenedSheet.getRange("A4:F4").values?.[0] ?? [];
const reopenedSlots = reopenedSheet.getRange("A5:F5").values?.[0] ?? [];
await reopened.inspect({
  kind: "formula",
  sheetId: "Sheet1",
  range: "A1:F5",
  options: { maxResults: 100 },
  summary: "final News export formula error scan",
});
const formulaMatrix = reopenedSheet.getRange("A1:F5").formulas;
const valueMatrix = reopenedSheet.getRange("A1:F5").values;
const formulaCount = formulaMatrix.flat().filter((value) => String(value ?? "").startsWith("=")).length;
const formulaErrorCount = valueMatrix
  .flat()
  .filter((value) => /#REF!|#DIV\/0!|#VALUE!|#NAME\?|#N\/A/.test(String(value ?? ""))).length;
await fs.mkdir(path.dirname(previewPath), { recursive: true });
const preview = await reopened.render({
  sheetName: "Sheet1",
  range: "A1:F7",
  scale: 2,
  format: "png",
});
await fs.writeFile(previewPath, new Uint8Array(await preview.arrayBuffer()));
const templateShaAfter = await sha256File(templatePath);

const validation = {
  schema_version: "news-excel-artifact-tool-validation-v1.0",
  exporter_version: EXPORTER_VERSION,
  mode,
  approval_path: approvalPath,
  approval_sha256: await sha256File(approvalPath),
  template_path: templatePath,
  template_sha256_before: templateShaBefore,
  template_sha256_after: templateShaAfter,
  output_path: outputPath,
  output_sha256: await sha256File(outputPath),
  preview_path: previewPath,
  sheet_names: reopenedSheetNames,
  row_4_headers: reopenedHeaders,
  row_5_slots: reopenedSlots,
  source_rows_1_4_values_preserved:
    JSON.stringify(sourceRowsOneToFour) === JSON.stringify(reopenedRowsOneToFour),
  formula_count: formulaCount,
  formula_error_count: formulaErrorCount,
  validations: {
    workbook_reopened: true,
    sheets_match_template:
      JSON.stringify(sourceSheetNames) === JSON.stringify(reopenedSheetNames),
    rows_1_4_values_preserved:
      JSON.stringify(sourceRowsOneToFour) === JSON.stringify(reopenedRowsOneToFour),
    row_4_headers_exact:
      JSON.stringify(reopenedHeaders) === JSON.stringify(EXPECTED_HEADERS),
    row_5_slots_exact: JSON.stringify(reopenedSlots) === JSON.stringify(slotTexts),
    source_template_unchanged: templateShaBefore === templateShaAfter,
    formula_errors_absent: formulaErrorCount === 0,
  },
};
validation.passed = Object.values(validation.validations).every(Boolean);
if (!validation.passed) {
  throw new Error(`News Excel artifact-tool validation failed: ${JSON.stringify(validation)}`);
}
await fs.mkdir(path.dirname(validationOutputPath), { recursive: true });
await fs.writeFile(validationOutputPath, JSON.stringify(validation, null, 2), "utf8");
console.log(JSON.stringify(validation));
