{
  "apl":"0.0.15","module":"v015_unknown_primitive_call","capabilities":[],
  "limits":{"steps":20,"output_lines":0,"host_reads":0},"invariants":[],"primitives":[],
  "entry":"main","functions":[{"name":"main","params":[],"returns":"i64","effects":[],"requires":[],"ensures":[],
  "body":[{"op":"const","id":"x","type":"i64","value":1},
  {"op":"primitive.call","id":"y","type":"i64","primitive":"p_0000000000000000000000000000000000000000000000000000000000000000","args":["x"]},
  {"op":"return","value":"y"}]}]
}
