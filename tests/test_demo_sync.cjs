/* GN-073: two independently rendered browser clients, late HTTP, reconnects. */
"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {createSync} = require("../app/static/demo_sync.js");

function sample(revision, step, stream_id="server-A") {
  return {mode:"synthetic_demo",stream_id,revision,step,total_steps:8,
    data:{match:{home:{name:"Azul"},away:{name:"Vermelho"}},
      ball:{uncertainty:"uncertain"},events:[],segments:[]}};
}
function browser() {
  const rendered=[],statuses=[],sockets=[],timers=[];
  let resolveHttp;
  const initial = new Promise(resolve => {resolveHttp=resolve;});
  const client=createSync({
    url:"ws://localhost:8000/ws",
    fetchState:()=>initial,
    createSocket:url=>{
      assert.equal(url,"ws://localhost:8000/ws");
      const socket={close(){this.onclose?.();},onopen:null,onmessage:null,
        onclose:null,onerror:null};
      sockets.push(socket);
      return socket;
    },
    render:snapshot=>rendered.push(snapshot),
    report:(message,online)=>statuses.push({message,online}),
    schedule:(fn,ms)=>{const item={fn,ms,cancelled:false};timers.push(item);return item;},
    cancel:item=>{item.cancelled=true;},
  });
  const deliver=(socket,payload)=>socket.onmessage({data:JSON.stringify(payload)});
  return {client,rendered,statuses,sockets,timers,deliver,resolveHttp};
}

test("two tabs converge for each ordered update, including reset and duplicates", async ()=>{
  const a=browser(),b=browser();
  a.client.start();b.client.start();
  assert.equal(a.sockets.length,1);
  assert.equal(b.sockets.length,1);
  a.sockets[0].onopen();b.sockets[0].onopen();
  const first=sample(0,0);
  for(const tab of [a,b])tab.deliver(tab.sockets[0],first);
  a.resolveHttp(sample(0,0));b.resolveHttp(sample(0,0));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(a.rendered.length,1);
  assert.equal(b.rendered.length,1);
  for(let revision=1;revision<=3;revision++){
    const state=sample(revision,revision);
    for(const tab of [a,b])tab.deliver(tab.sockets[0],state);
    // Return from an older concurrent HTTP command must not rewind the UI.
    assert.equal(a.client.accept(sample(revision-1,revision-1)),false);
    assert.equal(b.client.accept(state),false);
    assert.equal(a.rendered.at(-1).step,b.rendered.at(-1).step);
  }
  const reset=sample(4,0);
  for(const tab of [a,b])tab.deliver(tab.sockets[0],reset);
  assert.equal(a.rendered.at(-1).step,0);
  assert.equal(b.rendered.at(-1).step,0);
  assert.equal(a.rendered.length,5);
  assert.equal(b.rendered.length,5);
  a.client.stop();b.client.stop();
});

test("late first-load HTTP cannot overwrite a WebSocket snapshot",async ()=>{
  const tab=browser();
  tab.client.start();
  tab.deliver(tab.sockets[0],sample(5,5));
  tab.resolveHttp(sample(0,0));
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(tab.rendered.length,1);
  assert.equal(tab.rendered[0].revision,5);
  tab.client.stop();
});

test("reconnect restores snapshots, accepts restarted server and can be stopped",async ()=>{
  const tab=browser();
  tab.client.start();
  tab.resolveHttp(sample(2,2));
  await new Promise(resolve=>setImmediate(resolve));
  tab.sockets[0].onopen();
  tab.sockets[0].onclose();
  assert.equal(tab.timers[0].ms,1000);
  tab.timers[0].fn();
  assert.equal(tab.sockets.length,2);
  tab.sockets[1].onopen();
  tab.deliver(tab.sockets[1],sample(0,0,"server-B"));
  assert.equal(tab.rendered.at(-1).stream_id,"server-B");
  assert.deepEqual(tab.client.current(),{streamId:"server-B",revision:0});
  tab.client.stop();
  assert.equal(tab.sockets[1].onclose instanceof Function,true);
  assert.equal(tab.timers.length,1);
});

test("invalid data and unrelated media messages never reach render",async ()=>{
  const tab=browser();
  tab.client.start();
  tab.resolveHttp(sample(0,0));
  await new Promise(resolve=>setImmediate(resolve));
  const invalid=[
    null,{}, {mode:"persisted_match",stream_id:"A",revision:1,step:1,data:{}},
    {...sample(1,1),revision:-1},
    {...sample(1,1),data:{audio_base64:"AA=="}},
    {...sample(1,1),stream_id:""},
  ];
  for(const entry of invalid){
    assert.equal(tab.client.accept(entry),false);
  }
  tab.deliver(tab.sockets[0],sample(1,1));
  tab.deliver(tab.sockets[0],sample(0,0));
  assert.deepEqual(tab.rendered.map(value=>value.revision),[0,1]);
  tab.client.stop();
});
