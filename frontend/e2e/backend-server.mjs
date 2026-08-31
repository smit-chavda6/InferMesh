// Boots the gateway for Playwright: loads backend/.env, forces the dev cookie
// flag, and execs uvicorn. Playwright waits on /health before running specs.
import { spawn } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const backendDir = path.resolve(here, "../../backend");
const envPath = path.join(backendDir, ".env");

const env = {
  ...process.env,
  AUTH_COOKIE_SECURE: "false",
  // the suite authenticates once, but retries/reruns shouldn't trip the guard
  ADMIN_LOGIN_MAX_ATTEMPTS: "1000",
};
if (existsSync(envPath)) {
  for (const raw of readFileSync(envPath, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const m = line.match(/^([A-Za-z_][A-Za-z0-9_]*)=(.*)$/);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
}

const child = spawn(
  "uv",
  ["run", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
  { cwd: backendDir, env, stdio: "inherit", shell: true },
);

const stop = () => {
  child.kill();
  process.exit(0);
};
process.on("SIGINT", stop);
process.on("SIGTERM", stop);
child.on("exit", (code) => process.exit(code ?? 0));
