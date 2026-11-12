/* GN-070: deterministic 15-zone pitch geometry (drawing coordinates, not GPS). */
"use strict";
(function (root) {
  const LANES = ["left", "center", "right"];
  const DIRECTIONS = ["left_to_right", "right_to_left"];
  const WIDTH = 1000;
  const HEIGHT = 620;

  function zoneToGrid(zone, direction) {
    if (!zone || !Number.isInteger(zone.band) || zone.band < 1 || zone.band > 5 ||
        !LANES.includes(zone.lane) || !DIRECTIONS.includes(direction)) {
      throw new RangeError("Invalid pitch zone or attack direction");
    }
    const right = direction === "left_to_right";
    return {
      column: right ? zone.band - 1 : 5 - zone.band,
      row: zone.lane === "center" ? 1 :
        zone.lane === "left" ? (right ? 0 : 2) : (right ? 2 : 0),
    };
  }

  function zoneCellBounds(zone, direction, width = WIDTH, height = HEIGHT) {
    if (!Number.isFinite(width) || !Number.isFinite(height) ||
        width <= 0 || height <= 0) {
      throw new RangeError("Pitch width/height must be positive finite values");
    }
    const {column, row} = zoneToGrid(zone, direction);
    return {x: column * width / 5, y: row * height / 3,
            width: width / 5, height: height / 3};
  }

  function fieldCells(width = WIDTH, height = HEIGHT) {
    if (!Number.isFinite(width) || !Number.isFinite(height) ||
        width <= 0 || height <= 0) {
      throw new RangeError("Pitch width/height must be positive finite values");
    }
    const cells = [];
    for (let column = 0; column < 5; column++) {
      for (let row = 0; row < 3; row++) {
        cells.push({column, row, x: column * width / 5,
                    y: row * height / 3, width: width / 5,
                    height: height / 3});
      }
    }
    return cells;
  }

  function currentAttackDirection(direction, matchPeriod, observedPhase) {
    if (!DIRECTIONS.includes(direction)) throw new RangeError("Invalid attack direction");
    return observedPhase === "second_half" && matchPeriod !== "second_half" ?
      (direction === "left_to_right" ? "right_to_left" : "left_to_right") : direction;
  }

  const api = Object.freeze({WIDTH, HEIGHT, zoneToGrid, zoneCellBounds, fieldCells, currentAttackDirection});
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.GameNowField = api;
  }
})(typeof window !== "undefined" ? window : globalThis);
