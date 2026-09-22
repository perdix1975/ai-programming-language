{
  "apl": "0.0.3",
  "module": "wasm_scalar",
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
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
