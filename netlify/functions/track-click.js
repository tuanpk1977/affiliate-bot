const fs = require("fs");
const path = require("path");

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
  "click_quality_score",
];

exports.handler = async function handler(event) {
  if (event.httpMethod === "OPTIONS") {
    return response(204, "");
  }
  if (event.httpMethod !== "POST") {
    return response(405, { ok: false, error: "method_not_allowed" });
  }

  let payload;
  try {
    payload = JSON.parse(event.body || "{}");
  } catch (error) {
    return response(400, { ok: false, error: "invalid_json" });
  }

  const record = normalizeRecord(payload);
  const missing = validateRequired(record);
  if (missing.length) {
    console.log(JSON.stringify({ type: "affiliate_click_invalid", missing, record }));
    return response(400, { ok: false, error: "missing_required_fields", missing });
  }

  const isNetlifyProduction = process.env.NETLIFY === "true" && process.env.NETLIFY_DEV !== "true";
  const webhookUrl = String(process.env.CLICK_WEBHOOK_URL || "").trim();

  console.log(JSON.stringify({ type: "affiliate_click_event", record }));
  if (isNetlifyProduction) {
    if (webhookUrl) {
      await sendWebhook(webhookUrl, record);
    }
  } else {
    appendLocalCsv(record);
    if (webhookUrl) {
      await sendWebhook(webhookUrl, record);
    }
  }

  return response(200, {
    ok: true,
    mode: isNetlifyProduction ? "netlify_log" : "local_csv",
    persistent_storage: webhookUrl ? "webhook" : "not_configured",
  });
};

function normalizeRecord(payload) {
  const record = {};
  for (const column of COLUMNS) {
    record[column] = clean(payload[column]);
  }
  record.timestamp = record.timestamp || new Date().toISOString();
  record.cta_label = record.cta_label || clean(payload.cta);
  return record;
}

function validateRequired(record) {
  const required = ["click_id", "session_id", "tool_slug", "source_page", "cta_label", "timestamp"];
  return required.filter((column) => !record[column]);
}

function clean(value) {
  return String(value || "")
    .replace(/[\r\n\t]+/g, " ")
    .replace(/"/g, '""')
    .trim()
    .slice(0, 1000);
}

function appendLocalCsv(record) {
  const root = process.cwd();
  const dataDir = path.join(root, "data");
  const csvPath = path.join(dataDir, "click_events.csv");
  fs.mkdirSync(dataDir, { recursive: true });
  if (!fs.existsSync(csvPath)) {
    fs.writeFileSync(csvPath, COLUMNS.join(",") + "\n", "utf8");
  }
  const row = COLUMNS.map((column) => `"${record[column] || ""}"`).join(",");
  fs.appendFileSync(csvPath, row + "\n", "utf8");
}

async function sendWebhook(webhookUrl, record) {
  try {
    const result = await fetch(webhookUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(record),
    });
    if (!result.ok) {
      console.log(JSON.stringify({ type: "click_webhook_failed", status: result.status, statusText: result.statusText }));
    }
  } catch (error) {
    console.log(JSON.stringify({ type: "click_webhook_failed", message: error.message || String(error) }));
  }
}

function response(statusCode, body) {
  return {
    statusCode,
    headers: {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Content-Type": "application/json",
    },
    body: typeof body === "string" ? body : JSON.stringify(body),
  };
}
