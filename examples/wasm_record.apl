{
  "apl": "0.0.6",
  "module": "wasm_record",
  "entry": "main",
  "functions": [
    {
      "name": "score_of",
      "params": [
        {"name": "person", "type": {"record": {"age": "i64", "active": "bool"}}}
      ],
      "returns": "i64",
      "body": [
        {"op": "record.get", "id": "age", "type": "i64", "record": "person", "field": "age"},
        {"op": "return", "value": "age"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "age", "type": "i64", "value": 37},
        {"op": "const", "id": "active", "type": "bool", "value": true},
        {
          "op": "record",
          "id": "person",
          "type": {"record": {"age": "i64", "active": "bool"}},
          "fields": {"age": "age", "active": "active"}
        },
        {"op": "call", "id": "answer", "type": "i64", "function": "score_of", "args": ["person"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
