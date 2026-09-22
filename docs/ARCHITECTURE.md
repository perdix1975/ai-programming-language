# APL Architecture

APL separates **intent**, **normative semantics**, **verification**, and **execution strategy**.

```text
Human requirement
      |
      v
AI planner / programmer
      |
      v
Surface projection or structured generation
      |
      v
Canonical APL semantic IR
      |
      +--> verifier
      |
      +--> reference interpreter
      |
      +--> deterministic lowerer --> normalized CFG LIR --> optimizer --> backend --> native/WASM/accelerator target
      |
      +--> human explanation / audit projection
```

## Trusted semantic path

The initial trusted path is intentionally short:

```text
APL JSON IR -> verifier -> reference interpreter
```

The optimizer and compiler are not allowed to define new meaning. They must preserve the behavior defined by the semantic core.

## Repository layers

- `docs/`: language principles, normative draft specification, architecture and roadmap.
- `src/apl/verify.py`: structural, SSA and type verification.
- `src/apl/canonical.py`: deterministic canonical representation and identity.
- `src/apl/primitives.py`: content-addressed semantic primitive identity and deterministic primitive → core-function lowering.\n- `src/apl/lir.py`: deterministic semantic-IR → normalized CFG LIR lowering plus independent LIR verification.
- `src/apl/interpreter.py`: reference execution semantics.
- `src/apl/cli.py`: developer-facing bootstrap CLI.
- `examples/`: executable APL programs.
- `tests/`: semantic/conformance regression tests.

## Planned evolution

The next architectural layers are:

1. structured control flow and function calls;
2. richer structural/refinement types;
3. explicit effects and capabilities;
4. contracts/invariants;
5. collections and data-parallel operations;
6. normalized CFG lower IR (implemented as LIR 0.1);\n7. compact/binary LIR encoding and WASM/native backend;
8. optimizer with semantics-preserving transformations;
9. declarative constraint/search subsystem;
10. content-addressed machine-generated reusable primitives (initial pure mechanism implemented in Draft 0.0.15);
11. profile-guided and learned target optimization.

The Python implementation is a bootstrap reference, not a permanent performance dependency.
