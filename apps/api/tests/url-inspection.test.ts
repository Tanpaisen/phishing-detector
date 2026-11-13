import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { once } from "node:events";
import { createServer, type Server } from "node:http";
import type { AddressInfo } from "node:net";
import test from "node:test";
import express from "express";
import { createInspectionRouter } from "../src/url-inspection.js";

async function listen(server: Server) {
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  return `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
}

test("inspection gateway: validation, authentication forwarding, failures and rate limit", async t => {
  const fixture = JSON.parse(readFileSync(new URL("./fixtures/url-inspection.json", import.meta.url), "utf8"));
  let mode = "invalid-contract";
  let calls = 0;
  const upstream = createServer(async (req, res) => {
    calls++;
    assert.equal(req.headers["x-service-token"], "test-token");
    assert.equal(req.url, "/internal/v1/url/inspect");
    assert.ok(req.headers["x-request-id"]);
    if (mode === "timeout") { await new Promise(resolve => setTimeout(resolve, 400)); }
    res.setHeader("Content-Type", "application/json");
    if (mode === "success") {
      res.end(JSON.stringify(fixture));
    } else if (mode === "extra-nested-field") {
      const invalid = structuredClone(fixture);
      invalid.url.debug_token = "SECRET";
      res.end(JSON.stringify(invalid));
    } else if (mode === "validation") {
      res.statusCode = 422;
      res.end(JSON.stringify({ error: { code: "USERINFO_NOT_ALLOWED", message: "SECRET" } }));
    } else if (mode === "unauthorized") {
      res.statusCode = 401;
      res.end(JSON.stringify({ detail: "SECRET" }));
    } else {
      res.end(JSON.stringify({ status: "ok", risk_level: "SAFE", secret: "SECRET" }));
    }
  });
  const aiUrl = await listen(upstream);
  const app = express();
  app.use("/api/v1/url", createInspectionRouter({ aiUrl, aiToken: "test-token", timeoutMs: 100 }));
  const server = createServer(app);
  const apiUrl = await listen(server);
  t.after(() => {
    server.closeAllConnections(); server.close();
    upstream.closeAllConnections(); upstream.close();
  });
  const send = (body: string, type = "application/json") => fetch(`${apiUrl}/api/v1/url/inspect`, {
    method: "POST", headers: { "Content-Type": type }, body
  });
  const valid = JSON.stringify({ url: "https://example.com" });

  for (const [body, type, expected] of [
    ['{"url":"SECRET"', "application/json", 400],
    [valid, "text/plain", 415],
    [valid, "application/json; charset=iso-8859-1", 415],
    ['{"url":123}', "application/json", 422],
    ['{"url":"https://example.com","extra":"SECRET"}', "application/json", 422],
    [JSON.stringify({ url: "a".repeat(4097) }), "application/json", 422],
    [JSON.stringify({ url: "a".repeat(140000) }), "application/json", 413]
  ] as const) {
    const response = await send(body, type);
    assert.equal(response.status, expected);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.ok(response.headers.get("x-request-id"));
    assert.ok(!(await response.text()).includes("SECRET"));
  }
  assert.equal(calls, 0, "invalid client input must never reach Python");
  mode = "success";
  const success = await send(valid);
  assert.equal(success.status, 200);
  const result = await success.json();
  assert.equal(result.url.registered_domain, "example.com");
  assert.equal(result.model_loaded, false);
  assert.ok(!("risk_level" in result));
  for (const [upstreamMode, expectedStatus, expectedCode] of [
    ["extra-nested-field", 503, "AI_UNAVAILABLE"],
    ["invalid-contract", 503, "AI_UNAVAILABLE"],
    ["unauthorized", 503, "AI_UNAVAILABLE"],
    ["validation", 422, "USERINFO_NOT_ALLOWED"],
    ["timeout", 504, "AI_TIMEOUT"]
  ] as const) {
    mode = upstreamMode;
    const response = await send(valid);
    assert.equal(response.status, expectedStatus);
    const data = await response.json();
    assert.equal(data.error.code, expectedCode);
    assert.ok(!JSON.stringify(data).includes("SECRET"));
    assert.ok(!("risk_level" in data));
  }
  // 13 requests above; 47 more exhaust the 60-per-minute local limit.
  for (let i = 0; i < 47; i++) await send("{}");
  const throttled = await send(valid);
  assert.equal(throttled.status, 429);
  assert.ok(Number(throttled.headers.get("retry-after")) > 0);
});
