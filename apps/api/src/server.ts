import "dotenv/config";
import express from "express";
import { pool } from "./db.js";

const app = express();
const port = Number(process.env.PORT ?? 3001);

if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error("PORT phải là số nguyên từ 1 đến 65535.");
}

app.disable("x-powered-by");

// Kiểm tra tiến trình Backend đang hoạt động.
app.get("/api/v1/health", (_req, res) => {
  res.json({
    status: "ok",
    service: "phishing-detector-api"
  });
});

// Kiểm tra Backend có truy vấn được PostgreSQL hay không.
app.get("/api/v1/health/db", async (_req, res) => {
  try {
    const result = await pool.query(
      "SELECT current_database() AS database"
    );

    res.json({
      status: "ok",
      database: result.rows[0].database
    });
  } catch (error: unknown) {
    const code =
      typeof error === "object" &&
      error !== null &&
      "code" in error
        ? String(error.code)
        : "UNKNOWN";

    // Chỉ ghi mã lỗi, không ghi mật khẩu hoặc chuỗi kết nối.
    console.error("Kiểm tra PostgreSQL thất bại. Mã lỗi:", code);

    res.status(503).json({
      status: "error",
      message: "Không thể kết nối PostgreSQL."
    });
  }
});

app.get("/api/v1/health/ai", async (_req, res) => {
  const aiUrl = process.env.AI_SERVICE_URL;
  const aiToken = process.env.AI_SERVICE_TOKEN;

  if (!aiUrl || !aiToken) {
    res.status(503).json({
      status: "error",
      message: "Chưa cấu hình kết nối AI Service."
    });
    return;
  }

  try {
    const response = await fetch(
      new URL("/internal/v1/health", aiUrl),
      {
        headers: {
          "X-Service-Token": aiToken
        },
        signal: AbortSignal.timeout(3000),
        redirect: "error"
      }
    );

    if (!response.ok) {
      console.error("AI Service trả HTTP:", response.status);
      throw new Error("AI_SERVICE_ERROR");
    }

    const data: unknown = await response.json();

    if (
      typeof data !== "object" ||
      data === null ||
      !("status" in data) ||
      data.status !== "ok" ||
      !("service" in data) ||
      data.service !== "phishing-detector-ai" ||
      !("model_loaded" in data) ||
      typeof data.model_loaded !== "boolean"
    ) {
      throw new Error("INVALID_AI_RESPONSE");
    }

    res.json({
      status: "ok",
      service: "phishing-detector-api",
      ai: {
        status: data.status,
        service: data.service,
        model_loaded: data.model_loaded
      }
    });
  } catch (error: unknown) {
    const timedOut =
      error instanceof Error && error.name === "TimeoutError";

    res.status(timedOut ? 504 : 503).json({
      status: "error",
      message: timedOut
        ? "AI Service phản hồi quá thời gian cho phép."
        : "Không thể kết nối hoặc nhận phản hồi hợp lệ từ AI Service."
    });
  }
});

const server = app.listen(port, "127.0.0.1", () => {
  console.log(`Backend: http://127.0.0.1:${port}`);
});

server.on("error", (error: NodeJS.ErrnoException) => {
  console.error("Không thể khởi động Backend:", error.code);
  process.exit(1);
});

let shuttingDown = false;

function shutdown() {
  if (shuttingDown) return;
  shuttingDown = true;

  console.log("Đang dừng Backend...");

  const timeout = setTimeout(() => process.exit(1), 10000);
  timeout.unref();

  server.close(() => {
    void pool.end().then(
      () => process.exit(0),
      () => process.exit(1)
    );
  });
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);