{
  "apl": "0.0.6",
  "module": "wasm_struct_return",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": {
        "array": {
          "record": {
            "age": "i64",
            "name": "string"
          }
        },
        "len": 1
      },
      "body": [
        {
          "op": "const",
          "id": "name",
          "type": "string",
          "value": "Ada"
        },
        {
          "op": "const",
          "id": "age",
          "type": "i64",
          "value": 37
        },
        {
          "op": "record",
          "id": "person",
          "type": {
            "record": {
              "age": "i64",
              "name": "string"
            }
          },
          "fields": {
            "age": "age",
            "name": "name"
          }
        },
        {
          "op": "array",
          "id": "people",
          "type": {
            "array": {
              "record": {
                "age": "i64",
                "name": "string"
              }
            },
            "len": 1
          },
          "args": [
            "person"
          ]
        },
        {
          "op": "return",
          "value": "people"
        }
      ]
    }
  ]
}
