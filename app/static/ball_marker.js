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
  function distinguishActor(saved,input,marker,bounds){
    const actor=typeof input.actorId==="string"&&input.actorId.length>0&&input.actorId.length<=128?input.actorId:null;
    if(!marker.hasAnchor||!bounds)return marker;
    const key=[bounds.x,bounds.y,bounds.width,bounds.height].join(":");
    const sameArea=saved&&saved.visualAreaKey===key;
    const changed=actor&&saved?.actorId&&actor!==saved.actorId;
    let slot=0,illustrative=false;
    if(sameArea){slot=saved.visualSlot||0;illustrative=!!saved.illustrative;}
    // Only distinguish coincident/nearby drawing anchors. Never add drift on polling.
    if(changed&&Math.hypot(marker.x-saved.x,marker.y-saved.y)<60){
      slot=(saved.visualSlot||0)===0?1:0;illustrative=true;
    }
    const x=bounds.x+bounds.width/2+(slot?36:0);
    const y=bounds.y+bounds.height/2+(slot?18:0);
    return {...marker,x:Math.max(bounds.x+30,Math.min(bounds.x+bounds.width-30,x)),
      y:Math.max(bounds.y+30,Math.min(bounds.y+bounds.height-30,y)),
      actorId:actor||saved?.actorId||null,visualBounds:{...bounds},visualAreaKey:key,visualSlot:slot,illustrative,
      status:marker.status+(illustrative?". Deslocamento ilustrativo entre atletas; distância e direção não medidas":"")};
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
      return distinguishActor(saved,input,{...base,x:cell.x+cell.width/2,y:cell.y+cell.height/2,kind:"estimated",hasAnchor:true,
        status:"Bola representada na região estimada; não é posição exata"},cell);
    }
    const region=regionBounds(input.region);
    if(region)return distinguishActor(saved,input,{...base,x:region.x+region.width/2,y:region.y+region.height/2,kind:"partial",hasAnchor:true,
      status:"Símbolo na região estimada; posição exata da bola desconhecida"},region);
    const corridor=input.corridor;
    if(corridor&&lanes.includes(corridor.lane)&&
       (corridor.lane==="center"||directions.includes(corridor.attack_direction))){
      // Middle of the *drawing* is an anchor for the five-band corridor, not band 3 evidence.
      const cell=geometry.zoneCellBounds({band:3,lane:corridor.lane},corridor.attack_direction||"left_to_right");
      const area=regionBounds({bands:[1,2,3,4,5],lane:corridor.lane,attack_direction:corridor.attack_direction||"left_to_right"});
      return distinguishActor(saved,input,{...base,x:cell.x+cell.width/2,y:cell.y+cell.height/2,kind:"partial",hasAnchor:true,
        status:"Símbolo no corredor citado; faixa longitudinal desconhecida"},area);
    }
    if(saved&&saved.hasAnchor){
      return distinguishActor(saved,input,{...base,x:saved.x,y:saved.y,kind:"stale",hasAnchor:true,
        status:"Último marcador visual; posição atual desconhecida"},saved.visualBounds);
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
