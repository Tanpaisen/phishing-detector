import "dotenv/config";
import pg from "pg";

const { Pool } = pg;

export const pool = new Pool({
  max: 5,
  connectionTimeoutMillis: 3000,
  idleTimeoutMillis: 30000,
  statement_timeout: 5000
});

pool.on("error", () => {
  console.error("Kết nối PostgreSQL trong pool gặp lỗi.");
});