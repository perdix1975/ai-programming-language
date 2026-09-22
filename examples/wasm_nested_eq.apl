{
  "apl": "0.0.6",
  "module": "wasm_nested_eq",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "bool",
      "body": [
        {"op": "const", "id": "name1", "type": "string", "value": "Ada"},
        {"op": "const", "id": "name2", "type": "string", "value": "Ada"},
        {"op": "const", "id": "x1", "type": "i64", "value": 7},
        {"op": "const", "id": "y1", "type": "i64", "value": 9},
        {"op": "const", "id": "x2", "type": "i64", "value": 7},
        {"op": "const", "id": "y2", "type": "i64", "value": 9},
        {"op": "array", "id": "scores1", "type": {"array": "i64", "len": 2}, "args": ["x1", "y1"]},
        {"op": "array", "id": "scores2", "type": {"array": "i64", "len": 2}, "args": ["x2", "y2"]},
        {
          "op": "record",
          "id": "a",
          "type": {"record": {"name": "string", "scores": {"array": "i64", "len": 2}}},
          "fields": {"name": "name1", "scores": "scores1"}
        },
        {
          "op": "record",
          "id": "b",
          "type": {"record": {"name": "string", "scores": {"array": "i64", "len": 2}}},
          "fields": {"name": "name2", "scores": "scores2"}
        },
        {"op": "eq", "id": "answer", "type": "bool", "args": ["a", "b"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
