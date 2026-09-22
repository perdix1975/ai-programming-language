{
  "apl": "0.0.1",
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
        {"op": "eq", "id": "same", "type": "bool", "args": ["a", "b"]},
        {"op": "return", "value": "same"}
      ]
    }
  ]
}
