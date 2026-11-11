/* GN-066: deterministic, safe presentation of read-only fusion decisions. */
const test=require("node:test");
const assert=require("node:assert/strict");
const api=require("../app/static/fusion_diagnostics.js");

const match={home:{id:"team-azul"},away:{id:"team-rubro"}};
const sources=[{id:"radio-a",name:"Rádio A"},{id:"youtube-b",name:"YouTube B"}];

test("manual offsets are validated without mutating parsed evidence",()=>{
  const example=api.example(match,sources);
  const source=JSON.stringify(example);
  const prepared=api.prepare(source,[{source_id:"radio-a",seconds:0},
                                     {source_id:"youtube-b",seconds:8}]);
  assert.deepEqual(prepared.manual_offsets,[
    {source_id:"radio-a",seconds:0},{source_id:"youtube-b",seconds:8},
  ]);
  assert.equal(example.manual_offsets,undefined);
  assert.equal(prepared.selection.observations.length,2);
  assert.equal(prepared.fusion.observations[1].aligned_at,"2026-11-11T15:00:38Z");
});

test("invalid or duplicate manual calibration cannot run",()=>{
  const json=JSON.stringify(api.example(match,sources));
  for(const offsets of [
    [{source_id:"radio-a",seconds:""}],
    [{source_id:"radio-a",seconds:Infinity}],
    [{source_id:"radio-a",seconds:-121}],
    [{source_id:"radio-a",seconds:121}],
    [{source_id:"radio-a",seconds:0},{source_id:"radio-a",seconds:8}],
  ])assert.throws(()=>api.prepare(json,offsets));
  assert.throws(()=>api.prepare("{invalid",[]));
  assert.throws(()=>api.prepare("[]",[]));
});

test("sample requires two saved sources and identifies itself as fixture",()=>{
  assert.equal(api.example(match,sources.slice(0,1)),null);
  assert.equal(api.example(null,sources),null);
  const sample=api.example(match,sources);
  assert.equal(sample.selection.evaluated_at,sample.fusion.evaluated_at);
  assert.deepEqual(sample.fusion.observations.map(x=>x.source_id),["radio-a","youtube-b"]);
  assert.equal(sample.selection.observations[0].narration_kind,"live_play");
  assert.ok(sample.fusion.observations[0].segment_id.startsWith("example-"));
});

test("trace is converted into readable text without HTML injection",()=>{
  const result={
    trace:[
      {step:"source",source_id:"radio-a",status:"eligible",reason:"eligible"},
      {step:"manual_offset",source_id:"youtube-b",status:"preview_only",reason:"subtract_seconds=8"},
      {step:"fusion",source_id:"radio-a",status:"rejected",reason:"conflicting_source_evidence"},
    ],
    calibration:[
      {source_id:"youtube-b",original_aligned_at:"2026-11-11T15:00:38Z",
       preview_aligned_at:"2026-11-11T15:00:30Z",manual_offset_seconds:8},
    ],
  };
  const rows=api.describe(result,sources);
  assert.equal(rows.length,4);
  assert.match(rows[0].title,/Rádio A/);
  assert.match(rows[2].detail,/Contradição entre fontes/);
  assert.match(rows[3].detail,/correção 8 s, não persistida/);
  assert.throws(()=>api.describe({trace:null},sources));
});
