/* Persistent schematic symbol, kept separate from current ball/region evidence. */
"use strict";
(function(root){
  const geometry=typeof module==="object"&&module.exports?require("./field_geometry.js"):root.GameNowField;
  const lanes=["left","center","right"],directions=["left_to_right","right_to_left"];
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
  const api=Object.freeze({present,createMemory});
  if(typeof module==="object"&&module.exports)module.exports=api;
  else root.GameNowBallMarker=api;
})(typeof window!=="undefined"?window:globalThis);
