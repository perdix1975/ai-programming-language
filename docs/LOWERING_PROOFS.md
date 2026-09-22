# Semantic lowering certificates

Status: **M5 deterministic replay certificate v1**

APL Draft 0.0.15 semantic primitives are lowered to ordinary verified core functions before interpretation, LIR lowering, optimization, or backend compilation.

A lowering certificate makes that transformation independently checkable as an artifact.

## 1. Scope

The certificate is an explicit **deterministic replay proof/check**.

It is not a theorem-prover proof and it does not ask a consumer to trust compiler-produced claims. Verification re-runs the normative primitive lowerer from the source program and requires exact equality with both the supplied lowered-core artifact and the supplied certificate.

## 2. Artifact schema

A certificate contains exactly the deterministic information produced by:

```json
{
  "schema": "apl.lowering-proof.v1",
  "method": "deterministic-replay",
  "source_apl": "0.0.15",
  "source_hash": "<sha256>",
  "lowered_core_hash": "<sha256>",
  "primitive_mappings": [
    {
      "primitive": "p_<digest>",
      "function": "__apl_primitive_<digest>"
    }
  ],
  "call_sites": [
    {
      "path": "functions[0].body[1]",
      "primitive": "p_<digest>",
      "function": "__apl_primitive_<digest>"
    }
  ]
}
```

Primitive mappings are sorted by primitive id.

Call sites are recorded in deterministic source traversal order, including nested paths through `if.then`, `if.else`, and `repeat.body`.

## 3. Bound identities

`source_hash` is the canonical SHA-256 identity of the complete source APL program.

`lowered_core_hash` is the canonical SHA-256 identity of the exact core program produced by semantic primitive lowering.

The hashes are audit metadata; hash equality alone is not sufficient for verification.

## 4. Replay verification

Given:

1. source APL;
2. a claimed lowered-core artifact;
3. a claimed lowering certificate;

the checker:

1. fully verifies the source program;
2. runs the normative deterministic primitive lowerer;
3. constructs the expected certificate from that verified source;
4. requires exact structural equality between the supplied core and recomputed core;
5. requires exact structural equality between the supplied certificate and recomputed certificate;
6. defensively rechecks the source/core hashes and generated-function namespace.

Any modified source, primitive body, primitive id, call site, lowered instruction, generated function, mapping, or hash causes rejection.

## 5. CLI workflow

```text
apl lower-core source.apl > source.core.apl
apl lowering-proof source.apl > source.proof.json

apl verify-lowering-proof \
  source.apl \
  source.core.apl \
  source.proof.json
```

Successful verification prints:

```text
valid
```

The two artifact-producing commands are deterministic. Repeating them for identical canonical source produces byte-for-byte identical canonical JSON.

## 6. Security and trust model

The certificate does not make the lowerer untrusted by itself: replay verification still uses the reference lowering definition.

Its purpose is to make the transformation boundary explicit, portable, cacheable, and auditable.

A future independently implemented checker can validate the same certificate contract without depending on the Python implementation, because all certificate fields and the lowering rules are deterministic and specified.

## 7. Relationship to the compiler path

The lowered core is the semantic input already consumed by the interpreter/LIR pipeline after primitive expansion.

The certificate therefore bridges:

```text
content-addressed AI-native APL source
              |
              v
    deterministic replay proof
              |
              v
        ordinary core APL
              |
              v
       LIR -> optimizer -> WASM
```

No new runtime opcode, capability, effect, or execution semantic is introduced by certificates.

## 8. Conformance

CI checks:

- deterministic repeated core generation;
- deterministic repeated certificate generation;
- valid replay verification;
- source/core hash binding;
- primitive-id to generated-function mapping;
- source call-site mapping;
- nested call-site paths;
- rejection of tampered core artifacts;
- rejection of tampered certificates;
- rejection for pre-0.0.15 source programs.

This completes the M5 **explicit lowering proofs/checks** checkpoint.
