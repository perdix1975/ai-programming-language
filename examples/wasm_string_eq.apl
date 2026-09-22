{
  "apl": "0.0.6",
  "module": "wasm_string_eq",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "bool",
      "body": [
        {"op": "const", "id": "a", "type": "string", "value": "Καλημέρα"},
        {"op": "const", "id": "b", "type": "string", "value": "Καλημέρα"},
        {"op": "eq", "id": "answer", "type": "bool", "args": ["a", "b"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
