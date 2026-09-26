/** Geometry helpers for rendering a Bench 6 Vega-Lite point list as an SVG. */

export type PlotPoint = { x: number; y: number };

export type PlotBounds = {
  minX: number;
  maxX: number;
  minY: number;
  maxY: number;
};

export function asPlotPoints(value: unknown): PlotPoint[] {
  if (!Array.isArray(value)) return [];
  const points: PlotPoint[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const x = Number(record.x);
    const y = Number(record.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) continue;
    points.push({ x, y });
  }
  return points;
}

export function plotBounds(points: PlotPoint[]): PlotBounds | null {
  if (points.length === 0) return null;
  let minX = points[0].x;
  let maxX = points[0].x;
  let minY = points[0].y;
  let maxY = points[0].y;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }
  if (minX === maxX) {
    minX -= 1;
    maxX += 1;
  }
  if (minY === maxY) {
    minY -= 1;
    maxY += 1;
  }
  return { minX, maxX, minY, maxY };
}

export function projectPoint(
  point: PlotPoint,
  bounds: PlotBounds,
  width: number,
  height: number,
  pad: number,
): { x: number; y: number } {
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const x = pad + ((point.x - bounds.minX) / (bounds.maxX - bounds.minX)) * innerW;
  const y = pad + (1 - (point.y - bounds.minY) / (bounds.maxY - bounds.minY)) * innerH;
  return { x, y };
}

export function polylinePoints(
  points: PlotPoint[],
  bounds: PlotBounds,
  width: number,
  height: number,
  pad: number,
): string {
  return points
    .map((point) => {
      const projected = projectPoint(point, bounds, width, height, pad);
      return `${projected.x.toFixed(2)},${projected.y.toFixed(2)}`;
    })
    .join(" ");
}
