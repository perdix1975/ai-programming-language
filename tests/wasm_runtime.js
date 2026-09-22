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

  function readSlot(pointer, offset) {
    if (!state.memory) {
      throw new Error("APL WASM memory is not available");
    }
    const view = new DataView(state.memory.buffer);
    return view.getBigUint64(pointer + offset, true);
  }

  function slotPointer(slot) {
    return Number(slot & 0xffffffffn) >>> 0;
  }

  function slotSignedI64(slot) {
    return BigInt.asIntN(64, slot);
  }

  function compareSlot(type, leftSlot, rightSlot) {
    if (type === "i64") {
      return slotSignedI64(leftSlot) === slotSignedI64(rightSlot);
    }
    if (type === "bool") {
      return Number(leftSlot & 0xffffffffn) === Number(rightSlot & 0xffffffffn);
    }
    if (type === "string") {
      return (
        decodeString(slotSignedI64(leftSlot))
        === decodeString(slotSignedI64(rightSlot))
      );
    }
    if (type && typeof type === "object") {
      if ("array" in type && "len" in type) {
        return structuralEqual(
          type,
          slotPointer(leftSlot),
          slotPointer(rightSlot)
        );
      }
      if ("record" in type) {
        return structuralEqual(
          type,
          slotPointer(leftSlot),
          slotPointer(rightSlot)
        );
      }
      if ("range" in type || "quantity" in type) {
        return slotSignedI64(leftSlot) === slotSignedI64(rightSlot);
      }
    }
    throw new Error(`unsupported structural comparison type: ${JSON.stringify(type)}`);
  }

  function structuralEqual(type, leftPointer, rightPointer) {
    if (type && typeof type === "object" && "array" in type && "len" in type) {
      for (let index = 0; index < type.len; index += 1) {
        if (
          !compareSlot(
            type.array,
            readSlot(leftPointer, index * 8),
            readSlot(rightPointer, index * 8)
          )
        ) {
          return false;
        }
      }
      return true;
    }

    if (type && typeof type === "object" && "record" in type) {
      const fields = Object.keys(type.record).sort();
      for (let index = 0; index < fields.length; index += 1) {
        const field = fields[index];
        if (
          !compareSlot(
            type.record[field],
            readSlot(leftPointer, index * 8),
            readSlot(rightPointer, index * 8)
          )
        ) {
          return false;
        }
      }
      return true;
    }

    throw new Error(`struct_eq requires array/record descriptor, got ${JSON.stringify(type)}`);
  }

  function decodeSlotValue(type, slot) {
    if (type === "i64") {
      return slotSignedI64(slot).toString();
    }
    if (type === "bool") {
      return Number(slot & 0xffffffffn) !== 0;
    }
    if (type === "string") {
      return decodeString(slotSignedI64(slot));
    }
    if (type && typeof type === "object") {
      if ("range" in type || "quantity" in type) {
        return slotSignedI64(slot).toString();
      }
      if ("array" in type || "record" in type) {
        return decodeValue(type, slotPointer(slot));
      }
    }
    throw new Error(`unsupported slot decode type: ${JSON.stringify(type)}`);
  }

  function decodeValue(type, value) {
    if (type === "unit") return null;
    if (type === "i64") return BigInt(value).toString();
    if (type === "bool") return Boolean(value);
    if (type === "string") return decodeString(BigInt(value));

    if (type && typeof type === "object") {
      if ("range" in type || "quantity" in type) {
        return BigInt(value).toString();
      }
      if ("array" in type && "len" in type) {
        const pointer = Number(value) >>> 0;
        const result = [];
        for (let index = 0; index < type.len; index += 1) {
          result.push(
            decodeSlotValue(type.array, readSlot(pointer, index * 8))
          );
        }
        return result;
      }
      if ("record" in type) {
        const pointer = Number(value) >>> 0;
        const result = {};
        const fields = Object.keys(type.record).sort();
        for (let index = 0; index < fields.length; index += 1) {
          const field = fields[index];
          result[field] = decodeSlotValue(
            type.record[field],
            readSlot(pointer, index * 8)
          );
        }
        return result;
      }
    }

    throw new Error(`unsupported WASM result type: ${JSON.stringify(type)}`);
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
      require_host(kind) {
        if (!state.hostAvailable) {
          const label = kind === 1 ? "fs.read_text" : "net.get_text";
          const error = new Error(`HOST_UNAVAILABLE:${label}`);
          error.aplCode = "apl.host_unavailable";
          throw error;
        }
      },
      string_eq(left, right) {
        return decodeString(left) === decodeString(right) ? 1 : 0;
      },
      struct_eq(descriptorHandle, leftPointer, rightPointer) {
        const descriptor = JSON.parse(decodeString(descriptorHandle));
        return structuralEqual(
          descriptor,
          leftPointer >>> 0,
          rightPointer >>> 0
        ) ? 1 : 0;
      },
      application_trap(codeHandle, messageHandle, whereHandle) {
        const error = new Error(
          `APL_APPLICATION_TRAP:${decodeString(codeHandle)}:${decodeString(whereHandle)}:${decodeString(messageHandle)}`
        );
        error.aplCode = decodeString(codeHandle);
        error.aplMessage = decodeString(messageHandle);
        error.aplWhere = decodeString(whereHandle);
        throw error;
      },
      alloc(size) {
        if (!state.memory) {
          throw new Error("APL WASM memory is not available for allocation");
        }
        const aligned = (state.heap + 7) & ~7;
        const end = aligned + size;
        ensureCapacity(end);
        state.heap = end;
        return aligned;
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
    decodeValue,
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
