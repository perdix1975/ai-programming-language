# APL — AI Programming Language

APL is an experimental programming language and execution architecture designed **AI-first, semantics-first, and verification-first**.

The core idea is simple: the normative program should not be optimized for human typing. It should be an explicit typed semantic representation that AI systems can generate, verify, transform, optimize, explain, and compile.

> Status: **pre-alpha / Draft 0.0.1**

## What exists now

The first executable seed includes:

- versioned JSON semantic IR;
- SSA-style value identities;
- types: `i64`, `bool`, `string`, `unit`;
- operations: `const`, `add`, `sub`, `mul`, `eq`, `print`, `return`;
- strict verifier;
- deterministic canonical encoding and SHA-256 identity;
- reference interpreter;
- CLI;
- conformance tests and CI.

The Python implementation is a bootstrap reference implementation. It is not intended to be the final high-performance runtime.

## Try it

Requires Python 3.11+.

```bash
python -m pip install -e .
apl verify examples/hello.apl
apl run examples/hello.apl
apl canonicalize examples/hello.apl
apl hash examples/hello.apl
```

Expected execution:

```text
42
[return i64] 42
```

## First APL program

```json
{
  "apl": "0.0.1",
  "module": "hello",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 40},
        {"op": "const", "id": "b", "type": "i64", "value": 2},
        {"op": "add", "id": "answer", "type": "i64", "args": ["a", "b"]},
        {"op": "print", "args": ["answer"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
```

This representation is deliberately more machine-oriented than a conventional source language. Human-friendly projections can be added later without becoming the semantic foundation.

## Design documents

- [Language principles](docs/LANGUAGE_PRINCIPLES.md)
- [Draft v0 specification](docs/SPEC_v0.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Roadmap](docs/ROADMAP.md)

## Long-term direction

```text
Human intent
    |
    v
AI planner / programmer
    |
    v
APL semantic IR
    |
    +--> verifier
    +--> reference execution
    +--> human audit projection
    +--> optimizer --> WASM/native/accelerator backend
```

Future milestones add control flow, function calls, collections, explicit effects/capabilities, contracts, richer types, compilation, declarative solving, machine-generated primitives, and learned optimization.

## License

MIT.
