/* Persistent schematic symbol, kept separate from current ball/region evidence. */
"use strict";
(function(root){
  const geometry=typeof module==="object"&&module.exports?require("./field_geometry.js"):root.GameNowField;
  const lanes=["left","center","right"],directions=["left_to_right","right_to_left"];
  function regionBounds(region){
    if(!region||!Array.isArray(region.bands)||!region.bands.length||region.bands.length>5||
      !region.bands.every(b=>Number.isInteger(b)&&b>=1&&b<=5)||
      !(region.lane===null||lanes.includes(region.lane))||!directions.includes(region.attack_direction))return null;
    const cells=region.bands.flatMap(band=>(region.lane===null?lanes:[region.lane]).map(lane=>
      geometry.zoneCellBounds({band,lane},region.attack_direction)));
    const x=Math.min(...cells.map(c=>c.x)),y=Math.min(...cells.map(c=>c.y));
    return {x,y,width:Math.max(...cells.map(c=>c.x+c.width))-x,height:Math.max(...cells.map(c=>c.y+c.height))-y};
  }
  function present(previous,input){
    const context=input.context;
    if(typeof context!=="string"||!context)throw new TypeError("Marker context required");
    const timeline=Number.isFinite(input.timeline)?input.timeline:null;
    const epoch=input.epoch??null;
    const same=previous&&previous.context===context&&previous.epoch===epoch&&!input.reset&&
      !(timeline!==null&&previous.timeline!==null&&timeline<previous.timeline);
    const saved=same?previous:null;
    const base={context,epoch,timeline};
    const zone=input.zone;
    if(zone&&Number.isInteger(zone.band)&&zone.band>=1&&zone.band<=5&&
       lanes.includes(zone.lane)&&directions.includes(input.direction)){
      const cell=geometry.zoneCellBounds(zone,input.direction);
      return {...base,x:cell.x+cell.width/2,y:cell.y+cell.height/2,kind:"estimated",hasAnchor:true,
        status:"Bola representada no centro da região estimada; não é posição exata"};
    }
    const region=regionBounds(input.region);
    if(region)return {...base,x:region.x+region.width/2,y:region.y+region.height/2,kind:"partial",hasAnchor:true,
      status:"Símbolo na região citada; posição exata da bola desconhecida"};
    const corridor=input.corridor;
    if(corridor&&lanes.includes(corridor.lane)&&
       (corridor.lane==="center"||directions.includes(corridor.attack_direction))){
      // Middle of the *drawing* is an anchor for the five-band corridor, not band 3 evidence.
      const cell=geometry.zoneCellBounds({band:3,lane:corridor.lane},corridor.attack_direction||"left_to_right");
      return {...base,x:cell.x+cell.width/2,y:cell.y+cell.height/2,kind:"partial",hasAnchor:true,
        status:"Símbolo no centro do corredor citado; faixa longitudinal desconhecida"};
    }
    if(saved&&saved.hasAnchor){
      return {...base,x:saved.x,y:saved.y,kind:"stale",hasAnchor:true,
        status:"Último marcador visual; posição atual desconhecida"};
    }
    // Neutral drawing anchor stays inside the pitch; it is not location evidence.
    return {...base,x:500,y:310,kind:"unknown",hasAnchor:false,
      status:"Símbolo no círculo central; posição da bola desconhecida"};
  }
  function createMemory(maxContexts=32){
    if(!Number.isInteger(maxContexts)||maxContexts<1||maxContexts>128)throw new RangeError("Invalid marker memory bound");
    const records=new Map();
    return {update(input){
      const result=present(records.get(input.context),input);
      records.delete(input.context);records.set(input.context,result);
      while(records.size>maxContexts)records.delete(records.keys().next().value);
      return result;
    }};
  }
  const api=Object.freeze({present,createMemory,regionBounds});
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.GameNowBallMarker=api;
})(typeof window!=="undefined"?window:globalThis);
