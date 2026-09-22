"use strict";

const fs = require("fs");
const path = require("path");
const {isDeepStrictEqual} = require("util");
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

function loadJson(filename) {
  return JSON.parse(fs.readFileSync(filename, "utf8"));
}

function fixtureOptions(caseDef) {
  const options = {
    grants: caseDef.grants || [],
  };

  if (caseDef.host_available === false) {
    options.hostAvailable = false;
    return options;
  }

  if (caseDef.host_fixture) {
    const fixture = loadJson(caseDef.host_fixture);
    options.files = fixture.files || {};
    options.network = fixture.network || {};
  }
  return options;
}

function normalizeTrap(runtime, error, diagnostics) {
  let code = null;
  if (runtime.state.trapCode !== null) {
    code = TRAP_CODES[runtime.state.trapCode];
    if (!code) {
      throw new Error(
        `unknown compiled trap code ${runtime.state.trapCode}`
      );
    }
  } else if (error && error.aplCode) {
    code = error.aplCode;
  }

  if (!code) {
    throw error;
  }

  const outcome = {
    status: "trap",
    code,
    output: [...runtime.state.output],
  };
  if (diagnostics) {
    outcome.message = error.aplMessage;
    outcome.where = error.aplWhere;
  }
  return outcome;
}

async function runCompiled(caseDef, expected, wasmDir) {
  const wasmPath = path.join(wasmDir, `${caseDef.name}.wasm`);
  const runtime = await instantiateAplWasm(
    wasmPath,
    fixtureOptions(caseDef)
  );

  try {
    const raw = runtime.instance.exports.apl_entry();
    return {
      status: "ok",
      type: expected.type,
      value: runtime.decodeValue(expected.type, raw),
      output: [...runtime.state.output],
    };
  } catch (error) {
    return normalizeTrap(runtime, error, Boolean(caseDef.diagnostics));
  }
}

function canonicalJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function assertSame(name, expected, actual) {
  if (!isDeepStrictEqual(expected, actual)) {
    throw new Error(
      `differential mismatch for ${name}\nexpected: ${canonicalJson(expected)}\nactual:   ${canonicalJson(actual)}`
    );
  }
}

async function main() {
  const [manifestPath, referencePath, wasmDir] = process.argv.slice(2);
  if (!manifestPath || !referencePath || !wasmDir) {
    throw new Error(
      "usage: node tests/differential_wasm.js MANIFEST REFERENCE WASM_DIR"
    );
  }

  const manifest = loadJson(manifestPath);
  const reference = loadJson(referencePath);
  let passed = 0;

  for (const caseDef of manifest.cases) {
    const record = reference.cases[caseDef.name];
    if (!record) {
      throw new Error(`missing reference case ${caseDef.name}`);
    }
    const expected = record.outcome;
    const actual = await runCompiled(
      caseDef,
      expected,
      wasmDir
    );
    assertSame(caseDef.name, expected, actual);
    passed += 1;
  }

  process.stdout.write(
    `differential: ${passed} interpreter/WASM cases matched\n`
  );
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
