const SHEET_NAME = "click_events";

const COLUMNS = [
  "timestamp",
  "session_id",
  "click_id",
  "tool_slug",
  "tool_name",
  "source_page",
  "source_page_type",
  "cta_label",
  "target_url",
  "referrer",
  "event_type",
  "page_load_seconds",
  "user_agent_hint",
  "is_suspicious",
  "suspicious_reason",
  "click_quality_score"
];

function doPost(e) {
  const sheet = getOrCreateSheet_();
  const payload = parsePayload_(e);

  ensureHeader_(sheet);
  const row = COLUMNS.map(function(key) {
    return String(payload[key] || "");
  });
  sheet.appendRow(row);

  return jsonResponse_({
    ok: true,
    saved: true,
    sheet: SHEET_NAME,
    click_id: String(payload.click_id || "")
  });
}

function doGet() {
  return jsonResponse_({
    ok: true,
    message: "AI Tool Review Hub click webhook is running.",
    sheet: SHEET_NAME
  });
}

function getOrCreateSheet_() {
  const spreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  let sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    sheet = spreadsheet.insertSheet(SHEET_NAME);
  }
  return sheet;
}

function ensureHeader_(sheet) {
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(COLUMNS);
    return;
  }

  const currentHeader = sheet.getRange(1, 1, 1, COLUMNS.length).getValues()[0];
  const hasHeader = COLUMNS.every(function(column, index) {
    return currentHeader[index] === column;
  });
  if (!hasHeader) {
    sheet.insertRowBefore(1);
    sheet.getRange(1, 1, 1, COLUMNS.length).setValues([COLUMNS]);
  }
}

function parsePayload_(e) {
  try {
    return JSON.parse((e && e.postData && e.postData.contents) || "{}");
  } catch (err) {
    return {};
  }
}

function jsonResponse_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
