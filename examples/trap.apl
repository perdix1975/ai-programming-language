{
  "apl": "0.0.7",
  "module": "trap_demo",
  "entry": "main",
  "functions": [
    {
      "name": "main",
      "params": [],
      "returns": "i64",
      "body": [
        {
          "op": "trap",
          "code": "app.demo",
          "message": "demonstration trap"
        }
      ]
    }
  ]
}
