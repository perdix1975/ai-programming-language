{
  "apl": "0.0.10",
  "module": "wasm_output_limit_fail",
  "capabilities": ["console.write"],
  "limits": {"steps": 16, "output_lines": 0, "host_reads": 0},
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": ["console.write"],
      "body": [
        {"op": "const", "id": "message", "type": "string", "value": "blocked output"},
        {"op": "print", "args": ["message"]},
        {"op": "const", "id": "answer", "type": "i64", "value": 42},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
