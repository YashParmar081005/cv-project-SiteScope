// Start every E2E run from an empty test database and storage directory.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

export default function globalSetup() {
  const backend = path.resolve("../backend");
  const python = process.platform === "win32" ? path.join(backend, ".venv/Scripts/python.exe") : path.join(backend, ".venv/bin/python");
  execFileSync(python, ["-c", "import os; from pymongo import MongoClient; MongoClient(os.getenv('MONGO_URI', 'mongodb://localhost:27017')).drop_database('sitescope_e2e')"]);
  fs.rmSync(path.resolve("../data/e2e-storage"), { recursive: true, force: true });
}
