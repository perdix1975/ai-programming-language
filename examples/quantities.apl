{
  "apl": "0.0.13",
  "module": "quantities",
  "capabilities": [],
  "limits": {
    "steps": 32,
    "output_lines": 0,
    "host_reads": 0
  },
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "effects": [],
      "requires": [],
      "ensures": [],
      "body": [
        {"op": "const", "id": "distance_raw", "type": "i64", "value": 10},
        {"op": "const", "id": "time_raw", "type": "i64", "value": 2},
        {
          "op": "quantity.attach",
          "id": "distance",
          "type": {"quantity": {"m": 1}},
          "args": ["distance_raw"]
        },
        {
          "op": "quantity.attach",
          "id": "time",
          "type": {"quantity": {"s": 1}},
          "args": ["time_raw"]
        },
        {
          "op": "quantity.div",
          "id": "velocity",
          "type": {"quantity": {"m": 1, "s": -1}},
          "args": ["distance", "time"]
        },
        {
          "op": "quantity.value",
          "id": "raw_velocity",
          "type": "i64",
          "args": ["velocity"]
        },
        {"op": "return", "value": "raw_velocity"}
      ]
    }
  ]
}
