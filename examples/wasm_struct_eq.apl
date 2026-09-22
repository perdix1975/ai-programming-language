{
  "apl": "0.0.6",
  "module": "wasm_struct_eq",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "bool",
      "body": [
        {
          "op": "const",
          "id": "name_a",
          "type": "string",
          "value": "Ada"
        },
        {
          "op": "const",
          "id": "age_a",
          "type": "i64",
          "value": 37
        },
        {
          "op": "record",
          "id": "person_a",
          "type": {
            "record": {
              "age": "i64",
              "name": "string"
            }
          },
          "fields": {
            "age": "age_a",
            "name": "name_a"
          }
        },
        {
          "op": "const",
          "id": "name_b",
          "type": "string",
          "value": "Ada"
        },
        {
          "op": "const",
          "id": "age_b",
          "type": "i64",
          "value": 37
        },
        {
          "op": "record",
          "id": "person_b",
          "type": {
            "record": {
              "age": "i64",
              "name": "string"
            }
          },
          "fields": {
            "age": "age_b",
            "name": "name_b"
          }
        },
        {
          "op": "array",
          "id": "left",
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
            "person_a"
          ]
        },
        {
          "op": "array",
          "id": "right",
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
            "person_b"
          ]
        },
        {
          "op": "eq",
          "id": "same",
          "type": "bool",
          "args": [
            "left",
            "right"
          ]
        },
        {
          "op": "return",
          "value": "same"
        }
      ]
    }
  ]
}
