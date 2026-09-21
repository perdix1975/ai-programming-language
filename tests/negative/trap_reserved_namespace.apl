{
  "apl":"0.0.7",
  "module":"trap_reserved_namespace",
  "entry":"main",
  "functions":[
    {
      "name":"main",
      "params":[],
      "returns":"i64",
      "body":[
        {"op":"trap","code":"apl.i64_overflow","message":"forged runtime trap"}
      ]
    }
  ]
}
