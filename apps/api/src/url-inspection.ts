import { randomUUID } from "node:crypto";
import express, { type ErrorRequestHandler } from "express";

type Options = {
  aiUrl?: string;
  aiToken?: string;
  timeoutMs?: number;
};

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}

function validResult(value: unknown): value is Record<string, unknown> {
  if (!record(value) || value.schema_version !== "1.0" ||
      value.stage !== "URL_INSPECTION" || value.model_loaded !== false ||
      value.preprocessing_version !== "url-inspection-v1" ||
      !record(value.url) || !record(value.features) || !record(value.resources)) return false;
  if (!exactKeys(value, ["schema_version", "stage", "model_loaded", "preprocessing_version", "resources", "url", "features", "limitations"]) ||
      !exactKeys(value.url, ["normalized_url", "scheme", "hostname_input", "hostname_ascii", "hostname_unicode", "registered_domain", "public_suffix", "subdomain", "port", "is_ip", "is_private_suffix"]) ||
      !exactKeys(value.features, ["url_length", "hostname_length", "subdomain_count", "digit_count", "has_unicode_input", "has_unicode_hostname", "has_format_characters_in_hostname", "has_punycode_hostname", "has_query", "has_fragment"]) ||
      !exactKeys(value.resources, ["psl_sha256", "tldextract_version", "idna_version", "python_version", "unicode_version", "private_suffixes_included"])) return false;
  const url = value.url;
  const features = value.features;
  return ["normalized_url", "hostname_input", "hostname_ascii", "hostname_unicode", "public_suffix", "subdomain"]
      .every(key => typeof url[key] === "string") &&
    (url.scheme === "http" || url.scheme === "https") &&
    (url.registered_domain === null || typeof url.registered_domain === "string") &&
    (url.port === null || (Number.isInteger(url.port) && Number(url.port) >= 1 && Number(url.port) <= 65535)) &&
    typeof url.is_ip === "boolean" && typeof url.is_private_suffix === "boolean" &&
    ["url_length", "hostname_length", "subdomain_count", "digit_count"]
      .every(key => Number.isInteger(features[key]) && Number(features[key]) >= 0) &&
    ["has_unicode_input", "has_unicode_hostname", "has_format_characters_in_hostname", "has_punycode_hostname", "has_query", "has_fragment"]
      .every(key => typeof features[key] === "boolean") &&
    typeof value.resources.psl_sha256 === "string" &&
    /^[0-9a-f]{64}$/.test(value.resources.psl_sha256) &&
    typeof value.resources.idna_version === "string" &&
    typeof value.resources.python_version === "string" &&
    typeof value.resources.unicode_version === "string" &&
    typeof value.resources.tldextract_version === "string" &&
    value.resources.private_suffixes_included === true &&
    Array.isArray(value.limitations) && value.limitations.every(item => typeof item === "string");
}

// Local inspection endpoint. Does not create a scan or persist the URL.
export function createInspectionRouter(options: Options = {}) {
  const router = express.Router();
  const requests = new Map<string, { count: number; until: number }>();
  const error = (code: string, message: string, requestId: string) => ({
    request_id: requestId, error: { code, message }
  });

  router.use((_req, res, next) => {
    res.locals.requestId = randomUUID();
    res.set("Cache-Control", "no-store");
    res.set("X-Request-ID", res.locals.requestId);
    next();
  });

  router.post("/inspect", (req, res, next) => {
    const now = Date.now();
    for (const [key, entry] of requests) if (entry.until <= now) requests.delete(key);
    const key = req.ip ?? "unknown";
    const entry = requests.get(key) ?? { count: 0, until: now + 60000 };
    requests.set(key, entry);
    entry.count += 1;
    if (entry.count > 60) {
      res.set("Retry-After", String(Math.ceil((entry.until - now) / 1000)));
      res.status(429).json(error("RATE_LIMITED", "Vui lòng thử lại sau.", res.locals.requestId));
      return;
    }
    if (!req.is("application/json")) {
      res.status(415).json(error("UNSUPPORTED_MEDIA_TYPE", "Cần Content-Type application/json.", res.locals.requestId));
      return;
    }
    next();
  }, express.json({ limit: "128kb", strict: true }), async (req, res) => {
    const requestId: string = res.locals.requestId;
    if (!record(req.body) || Object.keys(req.body).length !== 1 ||
        typeof req.body.url !== "string" ||
        Array.from(req.body.url).length < 1 || Array.from(req.body.url).length > 4096) {
      res.status(422).json(error("INVALID_INPUT", "Cần một trường url dạng chuỗi, tối đa 4.096 ký tự.", requestId));
      return;
    }
    const aiUrl = options.aiUrl ?? process.env.AI_SERVICE_URL;
    const aiToken = options.aiToken ?? process.env.AI_SERVICE_TOKEN;
    if (!aiUrl || !aiToken) {
      res.status(503).json(error("AI_NOT_CONFIGURED", "Chưa cấu hình AI Service.", requestId));
      return;
    }
    try {
      const response = await fetch(new URL("/internal/v1/url/inspect", aiUrl), {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Service-Token": aiToken, "X-Request-ID": requestId },
        body: JSON.stringify({ url: req.body.url }),
        signal: AbortSignal.timeout(options.timeoutMs ?? 8000),
        redirect: "error"
      });
      const data: unknown = await response.json();
      if (response.status === 422) {
        // Allowlisted messages: never relay raw upstream errors or rejected input.
        const messages: Record<string, string> = {
          INVALID_INPUT: "Dữ liệu URL không hợp lệ.",
          INVALID_URL_LENGTH: "URL phải dài từ 1 đến 4.096 ký tự.",
          INVALID_URL: "URL không hợp lệ.",
          INVALID_HOST: "Hostname không hợp lệ.",
          INVALID_PORT: "Cổng không hợp lệ.",
          UNSUPPORTED_SCHEME: "Cần URL đầy đủ bắt đầu bằng http:// hoặc https://.",
          USERINFO_NOT_ALLOWED: "Không hỗ trợ URL chứa thông tin đăng nhập.",
          UNSUPPORTED_HOST: "Không hỗ trợ hostname nội bộ, IP đặc biệt hoặc hậu tố ngoài PSL cục bộ."
        };
        const code = record(data) && record(data.error) ? data.error.code : undefined;
        if (typeof code !== "string" || !Object.hasOwn(messages, code)) throw new Error("AI_CONTRACT_ERROR");
        res.status(422).json(error(code, messages[code]!, requestId));
        return;
      }
      if (!response.ok || !validResult(data)) throw new Error("AI_CONTRACT_ERROR");
      // Explicit projection prevents accidental future risk fields from leaking in.
      res.json({ request_id: requestId, schema_version: data.schema_version,
        stage: data.stage, model_loaded: false, preprocessing_version: data.preprocessing_version,
        resources: data.resources, url: data.url, features: data.features, limitations: data.limitations });
    } catch (err: unknown) {
      const timedOut = err instanceof Error && (err.name === "TimeoutError" || err.name === "AbortError");
      res.status(timedOut ? 504 : 503).json(error(
        timedOut ? "AI_TIMEOUT" : "AI_UNAVAILABLE",
        timedOut ? "AI Service phản hồi quá thời gian cho phép." : "AI Service không khả dụng hoặc phản hồi sai cấu trúc.", requestId));
    }
  });

  const handleBodyError: ErrorRequestHandler = (err: unknown, _req, res, _next) => {
    const type = record(err) ? err.type : undefined;
    const statuses: Record<string, number> = {
      "entity.too.large": 413, "entity.parse.failed": 400,
      "charset.unsupported": 415, "encoding.unsupported": 415,
      "request.aborted": 400, "request.size.invalid": 400
    };
    const status = typeof type === "string" && Object.hasOwn(statuses, type) ? statuses[type]! : 500;
    res.status(status).json(error(
      status === 413 ? "BODY_TOO_LARGE" : status === 400 ? "INVALID_JSON" : status === 415 ? "UNSUPPORTED_MEDIA_TYPE" : "INTERNAL_ERROR",
      status === 413 ? "Dữ liệu vượt giới hạn 128 KiB." : status === 400 ? "JSON không hợp lệ." : status === 415 ? "Charset hoặc content encoding không được hỗ trợ." : "Không thể xử lý yêu cầu.",
      res.locals.requestId));
  };
  router.use(handleBodyError);
  return router;
}
