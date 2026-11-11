"use strict";
const {test} = require("node:test");
const assert = require("node:assert/strict");
const {WIDTH, HEIGHT, zoneToGrid, zoneCellBounds, fieldCells} =
  require("../app/static/field_geometry.js");

test("the pitch contains exactly 15 non-overlapping full-size grid cells", () => {
  const cells = fieldCells();
  assert.equal(cells.length, 15);
  assert.equal(new Set(cells.map((c) => c.column + "-" + c.row)).size, 15);
  assert.ok(cells.every((c) => c.x >= 0 && c.y >= 0 &&
    c.x + c.width <= WIDTH && c.y + c.height <= HEIGHT));
  assert.equal(Math.round(cells.reduce((sum,c) => sum + c.width*c.height, 0)),
    WIDTH*HEIGHT);
});

test("all five bands and three corridors are distinct in either direction", () => {
  for (const direction of ["left_to_right", "right_to_left"]) {
    const locations = [];
    for (let band = 1; band <= 5; band++) {
      for (const lane of ["left", "center", "right"]) {
        const cell = zoneToGrid({band, lane}, direction);
        assert.ok(cell.column >= 0 && cell.column < 5);
        assert.ok(cell.row >= 0 && cell.row < 3);
        locations.push(cell.column + "-" + cell.row);
      }
    }
    assert.equal(new Set(locations).size, 15);
  }
});

test("the same attacking region reverses both axes after a side change", () => {
  for (let band = 1; band <= 5; band++) {
    for (const lane of ["left", "center", "right"]) {
      const a = zoneToGrid({band, lane}, "left_to_right");
      const b = zoneToGrid({band, lane}, "right_to_left");
      assert.equal(a.column + b.column, 4);
      assert.equal(a.row + b.row, 2);
    }
  }
});

test("the away team can attack opposite to the home team", () => {
  const zone = {band:5, lane:"left"};
  assert.deepEqual(zoneToGrid(zone,"left_to_right"),{column:4,row:0});
  assert.deepEqual(zoneToGrid(zone,"right_to_left"),{column:0,row:2});
});

test("small and desktop viewBoxes preserve identical normalized zone proportions", () => {
  const zone = {band:3,lane:"right"};
  const desktop = zoneCellBounds(zone, "right_to_left", 1000, 620);
  const mobile = zoneCellBounds(zone, "right_to_left", 320, 198.4);
  assert.equal(desktop.x/1000, mobile.x/320);
  assert.equal(desktop.y/620, mobile.y/198.4);
  assert.equal(desktop.width/1000, mobile.width/320);
  assert.equal(desktop.height/620, mobile.height/198.4);
  assert.equal(mobile.width, 64);
});

test("invalid regions and canvas sizes are never silently mapped", () => {
  for (const zone of [
    {band:0,lane:"center"}, {band:6,lane:"left"},
    {band:2,lane:"unknown"}, {band:2.5,lane:"right"}, null,
  ]) {
    assert.throws(() => zoneToGrid(zone,"left_to_right"), RangeError);
  }
  assert.throws(() => zoneToGrid({band:1,lane:"left"},"wrong"), RangeError);
  assert.throws(() => zoneCellBounds({band:1,lane:"left"},"left_to_right",0,620), RangeError);
  assert.throws(() => fieldCells(1000,-10), RangeError);
});
