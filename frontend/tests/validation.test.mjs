// Frontend validation tests — run with `npm test` (Node's built-in test runner, no dependencies).
import assert from "node:assert/strict";
import { test } from "node:test";

import { validateCredentials, validateProject, validateUpload } from "../js/validation.js";

const TODAY = "2026-10-17";
const PROJECT = { name: "Green Park Tower", construction_type: "residential_building",
  planned_start_date: "2025-01-01", target_completion_date: "2026-12-31" };

test("valid project has no errors", () => {
  assert.deepEqual(validateProject(PROJECT), {});
});

test("project name, type and dates are checked", () => {
  const e = validateProject({ ...PROJECT, name: "ab", construction_type: "castle", target_completion_date: "2024-01-01" });
  assert.deepEqual(Object.keys(e).sort(), ["construction_type", "name", "target_completion_date"]);
  assert.ok(validateProject({ ...PROJECT, planned_start_date: "" }).planned_start_date);
  assert.ok(validateProject({ ...PROJECT, name: "x".repeat(121) }).name);
});

test("photo upload validation", () => {
  const ok = { file: { type: "image/jpeg", size: 1000 }, captureDate: "2026-01-01" };
  assert.deepEqual(validateUpload(ok, { today: TODAY }), {});
  assert.ok(validateUpload({ ...ok, file: { type: "application/pdf", size: 10 } }, { today: TODAY }).file);
  assert.ok(validateUpload({ ...ok, file: { type: "image/png", size: 20 * 1048576 } }, { today: TODAY, maxMb: 15 }).file);
  assert.ok(validateUpload({ ...ok, captureDate: "2027-01-01" }, { today: TODAY }).capture_date);
  assert.ok(validateUpload({ ...ok, captureDate: "" }, { today: TODAY }).capture_date);
  assert.ok(validateUpload({ file: null, captureDate: "2026-01-01" }, { today: TODAY }).file);
});

test("credentials validation", () => {
  assert.deepEqual(validateCredentials({ email: "a@b.co", password: "x" }), {});
  assert.ok(validateCredentials({ email: "nope", password: "" }).email);
  assert.ok(validateCredentials({ email: "a@b.co", password: "short", name: "A" }, "register").password);
  assert.ok(validateCredentials({ email: "a@b.co", password: "long-enough", name: "" }, "register").name);
});
