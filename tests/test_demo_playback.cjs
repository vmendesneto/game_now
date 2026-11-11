"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const {create}=require("../app/static/demo_playback.js");
function fake(){
 const scheduled=[];
 return {scheduled,schedule:(fn,ms)=>{const task={fn,ms,cancelled:false};scheduled.push(task);return task;},
  cancel:task=>{task.cancelled=true;}};
}
test("start only creates one timer and advances at the expected cadence",async()=>{
 const c=fake();let n=0;
 const p=create({advance:async()=>({step:++n,total_steps:3}),schedule:c.schedule,cancel:c.cancel});
 assert.equal(p.start(),true);assert.equal(p.start(),false);
 assert.equal(c.scheduled.length,1);assert.equal(c.scheduled[0].ms,2500);
 await c.scheduled[0].fn();assert.equal(n,1);
 assert.equal(c.scheduled.length,2);p.pause();
 assert.equal(c.scheduled[1].cancelled,true);
});
test("pause stops without advancing; resume schedules a new step",async()=>{
 const c=fake();let n=0;
 const p=create({advance:async()=>({step:++n,total_steps:8}),schedule:c.schedule,cancel:c.cancel});
 p.start();p.pause();await c.scheduled[0].fn();
 assert.equal(n,0);assert.equal(p.running(),false);
 p.start();await c.scheduled[1].fn();assert.equal(n,1);p.pause();
});
test("final scenario step stops the timer automatically",async()=>{
 const c=fake(),p=create({advance:async()=>({step:8,total_steps:8}),
   schedule:c.schedule,cancel:c.cancel});
 p.start();await c.scheduled[0].fn();
 assert.equal(p.running(),false);assert.equal(c.scheduled.length,1);
});
test("remote browser advancing to final state pauses local playback",()=>{
 const c=fake(),p=create({advance:async()=>null,schedule:c.schedule,cancel:c.cancel});
 p.start();p.observe({step:8,total_steps:8});
 assert.equal(p.running(),false);assert.equal(c.scheduled[0].cancelled,true);
});
test("pause-and-drain waits for in-flight request before reset can run",async()=>{
 const c=fake();let finish;
 const p=create({advance:()=>new Promise(resolve=>{finish=resolve;}),
   schedule:c.schedule,cancel:c.cancel});
 p.start();const ongoing=c.scheduled[0].fn();
 await Promise.resolve();
 const waiting=p.pauseAndDrain();
 assert.equal(p.running(),false);
 finish({step:1,total_steps:8});
 await Promise.all([ongoing,waiting]);
 assert.equal(c.scheduled.length,1);
});
test("backend failure stops instead of retrying or duplicating requests",async()=>{
 const c=fake(),p=create({advance:async()=>null,schedule:c.schedule,cancel:c.cancel});
 p.start();await c.scheduled[0].fn();
 assert.equal(p.running(),false);assert.equal(c.scheduled.length,1);
});
