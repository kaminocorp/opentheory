import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { asPlotPoints, plotBounds, polylinePoints, projectPoint } from "./vega-lite-plot.ts";

describe("asPlotPoints", () => {
  it("keeps finite numeric pairs and drops the rest", () => {
    assert.deepEqual(
      asPlotPoints([
        { x: -3, y: 9 },
        { x: "nope", y: 1 },
        { x: 1, y: Number.NaN },
        { x: 3, y: 9 },
      ]),
      [
        { x: -3, y: 9 },
        { x: 3, y: 9 },
      ],
    );
  });
});

describe("plotBounds", () => {
  it("pads a degenerate single point so the scale is usable", () => {
    assert.deepEqual(plotBounds([{ x: 2, y: 5 }]), {
      minX: 1,
      maxX: 3,
      minY: 4,
      maxY: 6,
    });
  });

  it("returns null for an empty list", () => {
    assert.equal(plotBounds([]), null);
  });
});

describe("projectPoint / polylinePoints", () => {
  it("maps domain corners onto the padded svg box", () => {
    const bounds = plotBounds([
      { x: 0, y: 0 },
      { x: 10, y: 10 },
    ]);
    assert.ok(bounds);
    const topLeft = projectPoint({ x: 0, y: 10 }, bounds, 120, 80, 10);
    assert.equal(topLeft.x, 10);
    assert.equal(topLeft.y, 10);
    const bottomRight = projectPoint({ x: 10, y: 0 }, bounds, 120, 80, 10);
    assert.equal(bottomRight.x, 110);
    assert.equal(bottomRight.y, 70);
    assert.equal(
      polylinePoints(
        [
          { x: 0, y: 10 },
          { x: 10, y: 0 },
        ],
        bounds,
        120,
        80,
        10,
      ),
      "10.00,10.00 110.00,70.00",
    );
  });
});
