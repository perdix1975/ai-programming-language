{
  "apl": "0.0.11",
  "module": "wasm_postcondition_fail",
  "capabilities": [],
  "limits": {
    "steps": 64,
    "output_lines": 0,
    "host_reads": 0
  },
  "entry": "main",
  "functions": [
    {
      "name": "must_increase",
      "params": [
        {
          "name": "x",
          "type": "i64"
        }
      ],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [
        {
          "id": "increased",
          "message": "result must exceed x",
          "predicate": {
            "op": "gt",
            "args": [
              {
                "result": true
              },
              {
                "var": "x"
              }
            ]
          }
        }
      ],
      "body": [
        {
          "op": "return",
          "value": "x"
        }
      ]
    },
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [],
      "body": [
        {
          "op": "const",
          "id": "x",
          "type": "i64",
          "value": 3
        },
        {
          "op": "call",
          "id": "answer",
          "type": "i64",
          "function": "must_increase",
          "args": [
            "x"
          ]
        },
        {
          "op": "return",
          "value": "answer"
        }
      ]
    }
  ]
}
