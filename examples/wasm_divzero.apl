{
  "apl": "0.0.3",
  "module": "wasm_divzero",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "a", "type": "i64", "value": 7},
        {"op": "const", "id": "b", "type": "i64", "value": 0},
        {"op": "div", "id": "answer", "type": "i64", "args": ["a", "b"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
