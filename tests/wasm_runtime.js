"use strict";

const fs = require("fs");

const CAPABILITY_BITS = {
  "console.write": 1,
  "fs.read_text": 2,
  "net.get_text": 4,
};

function capabilityMask(names) {
  let mask = 0;
  for (const name of names || []) {
    if (!(name in CAPABILITY_BITS)) {
      throw new Error(`unknown APL WASM capability: ${name}`);
    }
    mask |= CAPABILITY_BITS[name];
  }
  return mask;
}

function unpackHandle(handle) {
  const raw = BigInt.asUintN(64, handle);
  return {
    pointer: Number((raw >> 32n) & 0xffffffffn),
    length: Number(raw & 0xffffffffn),
  };
}

function packHandle(pointer, length) {
  return BigInt.asIntN(
    64,
    (BigInt(pointer) << 32n) | BigInt(length)
  );
}

async function instantiateAplWasm(path, options = {}) {
  const state = {
    memory: null,
    heap: 0,
    output: [],
    trapCode: null,
    grants: capabilityMask(options.grants || []),
    files: {...(options.files || {})},
    network: {...(options.network || {})},
    hostAvailable: options.hostAvailable !== false,
  };
  const decoder = new TextDecoder("utf-8", {fatal: true});
  const encoder = new TextEncoder();

  function decodeString(handle) {
    if (!state.memory) {
      throw new Error("APL WASM memory is not available");
    }
    const {pointer, length} = unpackHandle(handle);
    const bytes = new Uint8Array(
      state.memory.buffer,
      pointer,
      length
    );
    return decoder.decode(bytes);
  }

  function ensureCapacity(end) {
    const current = state.memory.buffer.byteLength;
    if (end <= current) return;
    const extraBytes = end - current;
    const pages = Math.ceil(extraBytes / 65536);
    state.memory.grow(pages);
  }

  function allocateString(value) {
    const bytes = encoder.encode(value);
    const pointer = state.heap;
    const end = pointer + bytes.length;
    ensureCapacity(end);
    new Uint8Array(state.memory.buffer, pointer, bytes.length).set(bytes);
    state.heap = end;
    return packHandle(pointer, bytes.length);
  }

  function requireHost(kind) {
    if (!state.hostAvailable) {
      const error = new Error(`HOST_UNAVAILABLE:${kind}`);
      error.aplCode = "apl.host_unavailable";
      throw error;
    }
  }

  const imports = {
    apl: {
      trap(code) {
        state.trapCode = code;
        const error = new Error(`APL_WASM_TRAP:${code}`);
        error.aplTrapCode = code;
        throw error;
      },
      require_capabilities(mask) {
        const missing = mask & ~state.grants;
        if (missing !== 0) {
          const error = new Error(`CAPABILITY_DENIED:${missing}`);
          error.aplCode = "apl.capability_denied";
          error.missingMask = missing;
          throw error;
        }
      },
      string_eq(left, right) {
        return decodeString(left) === decodeString(right) ? 1 : 0;
      },
      console_write_i64(value) {
        state.output.push(value.toString());
      },
      console_write_bool(value) {
        state.output.push(value ? "true" : "false");
      },
      console_write_string(handle) {
        state.output.push(decodeString(handle));
      },
      fs_read_text(handle) {
        requireHost("fs.read_text");
        const key = decodeString(handle);
        if (!(key in state.files)) {
          const error = new Error(`HOST_RESOURCE_MISSING:path:${key}`);
          error.aplCode = "apl.host_resource_missing";
          throw error;
        }
        return allocateString(state.files[key]);
      },
      net_get_text(handle) {
        requireHost("net.get_text");
        const key = decodeString(handle);
        if (!(key in state.network)) {
          const error = new Error(`HOST_RESOURCE_MISSING:url:${key}`);
          error.aplCode = "apl.host_resource_missing";
          throw error;
        }
        return allocateString(state.network[key]);
      },
    },
  };

  const bytes = fs.readFileSync(path);
  const {instance} = await WebAssembly.instantiate(bytes, imports);
  state.memory = instance.exports.memory || null;
  if (state.memory) {
    const staticEnd = instance.exports.apl_static_end;
    state.heap = staticEnd ? Number(staticEnd.value) : 0;
  }

  return {
    instance,
    state,
    decodeString,
    allocateString,
  };
}

module.exports = {
  CAPABILITY_BITS,
  capabilityMask,
  instantiateAplWasm,
  packHandle,
  unpackHandle,
};
