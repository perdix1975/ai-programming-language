{
  "apl": "0.0.6",
  "module": "wasm_record_string",
  "entry": "main",
  "functions": [
    {
      "name": "name_is_ada",
      "params": [
        {"name": "person", "type": {"record": {"name": "string", "age": "i64"}}}
      ],
      "returns": "bool",
      "body": [
        {"op": "record.get", "id": "name", "type": "string", "record": "person", "field": "name"},
        {"op": "const", "id": "expected", "type": "string", "value": "Ada"},
        {"op": "eq", "id": "same", "type": "bool", "args": ["name", "expected"]},
        {"op": "return", "value": "same"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "bool",
      "body": [
        {"op": "const", "id": "name", "type": "string", "value": "Ada"},
        {"op": "const", "id": "age", "type": "i64", "value": 37},
        {
          "op": "record",
          "id": "person",
          "type": {"record": {"name": "string", "age": "i64"}},
          "fields": {"name": "name", "age": "age"}
        },
        {"op": "call", "id": "answer", "type": "bool", "function": "name_is_ada", "args": ["person"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
