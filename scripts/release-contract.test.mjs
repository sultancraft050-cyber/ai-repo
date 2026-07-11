import assert from "node:assert/strict";
import test from "node:test";
import { compareReleaseContracts } from "./release-contract.mjs";

const backend = { service: "backend", release: "0.1.0", api_contract_version: "1" };

test("accepts matching API contract versions even when releases differ", () => {
  const result = compareReleaseContracts(
    { service: "frontend", release: "0.1.1", api_contract_version: "1" },
    backend,
  );
  assert.equal(result.status, "compatible");
});

test("rejects mismatched API contract versions", () => {
  const result = compareReleaseContracts(
    { service: "frontend", release: "0.1.1", api_contract_version: "2" },
    backend,
  );
  assert.equal(result.status, "incompatible");
});

test("reports missing metadata as unverifiable", () => {
  const result = compareReleaseContracts(null, backend);
  assert.equal(result.status, "unverifiable");
});
