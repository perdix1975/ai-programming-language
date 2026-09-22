"use strict";

const fs = require("fs");
const {instantiateAplWasm} = require("./wasm_runtime.js");

const TRAP_CODES = {
  1: "apl.i64_overflow",
  2: "apl.division_by_zero",
  3: "apl.repeat_negative_count",
  4: "apl.repeat_count_exceeds_max",
  5: "apl.resource_limit",
  6: "apl.precondition_failed",
  7: "apl.postcondition_failed",
  8: "apl.invariant_failed",
  9: "apl.range_violation",
  10: "apl.array_index_oob",
};

async function execute(path, item) {
  const host = item.host;
  const runtime = await instantiateAplWasm(path, {
    grants: item.grants || [],
    files: host ? host.files || {} : {},
    network: host ? host.network || {} : {},
    hostAvailable: host !== null,
  });

  try {
    const raw = runtime.instance.exports.apl_entry();
    return {
      kind: "return",
      type: item.return_type,
      value: runtime.decodeValue(item.return_type, raw),
      output: [...runtime.state.output],
    };
  } catch (err) {
    const code =
      err.aplCode
      || TRAP_CODES[runtime.state.trapCode]
      || null;
    if (!code) {
      throw err;
    }
    return {
      kind: "trap",
      code,
      output: [...runtime.state.output],
    };
  }
}

function same(left, right) {
  return JSON.stringify(left) === JSON.stringify(right);
}

async function main() {
  const planPath = process.argv[2];
  if (!planPath) {
    throw new Error("usage: node tests/wasm_differential.js PLAN.json");
  }
  const plan = JSON.parse(fs.readFileSync(planPath, "utf8"));
  let checked = 0;

  for (const item of plan) {
    const baseline = await execute(item.baseline, item);
    const optimized = await execute(item.optimized, item);

    if (!same(baseline, item.expected)) {
      throw new Error(
        `differential mismatch [${item.id}] baseline\n`
        + `expected=${JSON.stringify(item.expected)}\n`
        + `actual=${JSON.stringify(baseline)}`
      );
    }
    if (!same(optimized, item.expected)) {
      throw new Error(
        `optimization mismatch [${item.id}] optimized\n`
        + `expected=${JSON.stringify(item.expected)}\n`
        + `actual=${JSON.stringify(optimized)}`
      );
    }
    if (!same(optimized, baseline)) {
      throw new Error(
        `baseline/optimized mismatch [${item.id}]\n`
        + `baseline=${JSON.stringify(baseline)}\n`
        + `optimized=${JSON.stringify(optimized)}`
      );
    }
    checked += 1;
  }

  console.log(
    `WASM differential outcomes matched interpreter for ${checked} cases`
  );
}

main().catch((err) => {
  console.error(err && err.stack ? err.stack : err);
  process.exit(1);
});
