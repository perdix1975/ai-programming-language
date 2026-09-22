{
  "apl": "0.0.10",
  "module": "wasm_steps_fail",
  "capabilities": [],
  "limits": {
    "steps": 3,
    "output_lines": 0,
    "host_reads": 0
  },
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 40},
        {"op": "const", "id": "b", "type": "i64", "value": 2},
        {"op": "add", "id": "answer", "type": "i64", "args": ["a", "b"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
