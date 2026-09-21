{
  "apl": "0.0.6",
  "module": "records",
  "entry": "main",
  "functions": [
    {
      "name": "age_of",
      "params": [
        {
          "name": "person",
          "type": {
            "record": {
              "name": "string",
              "age": "i64"
            }
          }
        }
      ],
      "returns": "i64",
      "body": [
        {
          "op": "record.get",
          "id": "age",
          "type": "i64",
          "record": "person",
          "field": "age"
        },
        {"op": "return", "value": "age"}
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {"op": "const", "id": "name", "type": "string", "value": "Ada"},
        {"op": "const", "id": "age", "type": "i64", "value": 37},
        {
          "op": "record",
          "id": "person",
          "type": {
            "record": {
              "name": "string",
              "age": "i64"
            }
          },
          "fields": {
            "age": "age",
            "name": "name"
          }
        },
        {
          "op": "call",
          "id": "answer",
          "type": "i64",
          "function": "age_of",
          "args": ["person"]
        },
        {"op": "print", "args": ["answer"]},
        {"op": "return", "value": "answer"}
      ]
    }
  ]
}
