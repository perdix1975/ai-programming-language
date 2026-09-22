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
        {"op": "const", "id": "c", "type": "string", "value": "καλημέρα"},
        {"op": "eq", "id": "same", "type": "bool", "args": ["a", "b"]},
        {"op": "eq", "id": "different", "type": "bool", "args": ["a", "c"]},
        {"op": "not", "id": "not_different", "type": "bool", "args": ["different"]},
        {"op": "and", "id": "answer", "type": "bool", "args": ["same", "not_different"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
