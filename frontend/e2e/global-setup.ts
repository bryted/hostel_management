import { execFileSync } from "node:child_process";
import path from "node:path";
import fs from "node:fs";

async function globalSetup() {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const python = process.platform === "win32"
    ? path.join(repoRoot, ".venv", "Scripts", "python.exe")
    : path.join(repoRoot, ".venv", "bin", "python");
  const executable = fs.existsSync(python) ? python : "python";
  execFileSync(executable, ["-m", "app.scripts.seed_e2e_data"], {
    cwd: repoRoot,
    stdio: "inherit",
  });
}

export default globalSetup;
