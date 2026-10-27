// Turns the Manhattan grid (card 12) into one smooth image for the map.
//
// Each grid cell is a point with a value (a score, or 1/0 for a gap). The
// value at any spot on the image is a weighted average of the nearby points,
// with weights that fall off smoothly with distance (a Gaussian, sigma in
// grid cells). Dividing by the summed weights ("normalized convolution")
// keeps edges and small holes from fading toward zero: a small park is filled
// in by its neighbors, while the far edge of the data fades out softly. The
// image is then cut to Manhattan's shoreline so nothing spills into the
// rivers, and parks and lakes are cut out of it, since nobody lives there.

const M_PER_DEG_LAT = 110_540;
// build_grid.py spaces columns using the longitude scale at this latitude.
const GRID_LAT0 = 40.78;
// Image pixels per grid cell. The browser smooths it further when zooming in.
const PIXELS_PER_CELL = 6;

// Leaflet stretches an image evenly in Web Mercator, not in latitude, so
// image rows are placed by Mercator y.
const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));
const latFromMercY = (y) => ((2 * Math.atan(Math.exp(y)) - Math.PI / 2) * 180) / Math.PI;

export function smoothstep(edge0, edge1, x) {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

function gaussianKernel(sigma) {
  const radius = Math.ceil(3 * sigma);
  const weights = [];
  for (let i = -radius; i <= radius; i++) weights.push(Math.exp(-(i * i) / (2 * sigma * sigma)));
  const sum = weights.reduce((a, b) => a + b, 0);
  return { radius, weights: weights.map((w) => w / sum) };
}

// A Gaussian blur, done as two 1-D passes (across, then down).
function blur(source, cols, rows, { radius, weights }) {
  const across = new Float32Array(source.length);
  const out = new Float32Array(source.length);
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      let sum = 0;
      for (let i = -radius; i <= radius; i++) {
        const xx = x + i;
        if (xx >= 0 && xx < cols) sum += source[y * cols + xx] * weights[i + radius];
      }
      across[y * cols + x] = sum;
    }
  }
  for (let y = 0; y < rows; y++) {
    for (let x = 0; x < cols; x++) {
      let sum = 0;
      for (let i = -radius; i <= radius; i++) {
        const yy = y + i;
        if (yy >= 0 && yy < rows) sum += across[yy * cols + x] * weights[i + radius];
      }
      out[y * cols + x] = sum;
    }
  }
  return out;
}

// Bilinear lookup in a cols x rows array at fractional (gx, gy).
function sample(field, cols, rows, gx, gy) {
  const x0 = Math.max(0, Math.min(cols - 2, Math.floor(gx)));
  const y0 = Math.max(0, Math.min(rows - 2, Math.floor(gy)));
  const tx = Math.min(1, Math.max(0, gx - x0));
  const ty = Math.min(1, Math.max(0, gy - y0));
  const i = y0 * cols + x0;
  const top = field[i] * (1 - tx) + field[i + 1] * tx;
  const bottom = field[i + cols] * (1 - tx) + field[i + cols + 1] * tx;
  return top * (1 - ty) + bottom * ty;
}

// Returns { url, bounds } for L.imageOverlay.
//   valueFor(cell): a number, or null for "no data here" (big parks).
//   colorFor(value): [r, g, b, alpha 0-1], or null to leave the spot clear.
//   sigma: how far the smoothing reaches, in grid cells.
//   land: outlines to keep, as [[lat, lng], ...]; blank: outlines to cut out.
export function gridImage({ cells, cellM, valueFor, colorFor, sigma, land, blank = [] }) {
  const stepLat = cellM / M_PER_DEG_LAT;
  const stepLng = cellM / (111_320 * Math.cos((GRID_LAT0 * Math.PI) / 180));
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const [lat, lng] of cells) {
    minLat = Math.min(minLat, lat);
    maxLat = Math.max(maxLat, lat);
    minLng = Math.min(minLng, lng);
    maxLng = Math.max(maxLng, lng);
  }

  // A margin of empty cells so the fade at the edges isn't cut off.
  const kernel = gaussianKernel(sigma);
  const pad = kernel.radius + 1;
  const cols = Math.round((maxLng - minLng) / stepLng) + 1 + 2 * pad;
  const rows = Math.round((maxLat - minLat) / stepLat) + 1 + 2 * pad;
  const lat0 = minLat - pad * stepLat;
  const lng0 = minLng - pad * stepLng;

  // Row 0 is the south edge here. isLand marks every grid cell; hasData
  // only those with a value, so parks (no value) can be told from water.
  const values = new Float32Array(cols * rows);
  const hasData = new Float32Array(cols * rows);
  const isLand = new Float32Array(cols * rows);
  for (const cell of cells) {
    const x = Math.round((cell[1] - lng0) / stepLng);
    const y = Math.round((cell[0] - lat0) / stepLat);
    isLand[y * cols + x] = 1;
    const value = valueFor(cell);
    if (value === null) continue;
    values[y * cols + x] = value;
    hasData[y * cols + x] = 1;
  }
  const valueSum = blur(values, cols, rows, kernel);
  const weightSum = blur(hasData, cols, rows, kernel);
  const landSum = blur(isLand, cols, rows, kernel);

  const south = lat0, north = lat0 + (rows - 1) * stepLat;
  const west = lng0, east = lng0 + (cols - 1) * stepLng;
  const width = (cols - 1) * PIXELS_PER_CELL;
  const height = (rows - 1) * PIXELS_PER_CELL;
  const yNorth = mercY(north), ySouth = mercY(south);

  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(width, height);
  for (let py = 0; py < height; py++) {
    const lat = latFromMercY(yNorth - ((py + 0.5) / height) * (yNorth - ySouth));
    const gy = (lat - lat0) / stepLat;
    for (let px = 0; px < width; px++) {
      const gx = (px + 0.5) / PIXELS_PER_CELL;
      const weight = sample(weightSum, cols, rows, gx, gy);
      if (weight < 0.05) continue;
      const color = colorFor(sample(valueSum, cols, rows, gx, gy) / weight);
      if (!color) continue;
      // Full color everywhere people live, right up to the shoreline (the
      // image is cut to it below). Only where most nearby land is park
      // (cells with no value), such as a highway strip running through a
      // park, does the color drop out.
      const land = sample(landSum, cols, rows, gx, gy);
      const alpha = color[3] * smoothstep(0.25, 0.4, weight / land);
      const i = (py * width + px) * 4;
      image.data[i] = color[0];
      image.data[i + 1] = color[1];
      image.data[i + 2] = color[2];
      image.data[i + 3] = Math.round(alpha * 255);
    }
  }
  ctx.putImageData(image, 0, 0);

  // Cut to the shoreline: draw the land outlines as a clipping path, then
  // the image through it. Then erase the parks and lakes.
  const clipped = document.createElement("canvas");
  clipped.width = width;
  clipped.height = height;
  const clipCtx = clipped.getContext("2d");
  const trace = (rings) => {
    clipCtx.beginPath();
    for (const ring of rings) {
      ring.forEach(([lat, lng], k) => {
        const x = ((lng - west) / (east - west)) * width;
        const y = ((yNorth - mercY(lat)) / (yNorth - ySouth)) * height;
        if (k === 0) clipCtx.moveTo(x, y);
        else clipCtx.lineTo(x, y);
      });
      clipCtx.closePath();
    }
  };
  trace(land);
  clipCtx.clip();
  clipCtx.drawImage(canvas, 0, 0);
  if (blank.length) {
    clipCtx.globalCompositeOperation = "destination-out"; // drawing erases
    trace(blank);
    clipCtx.fill("nonzero");
  }

  return {
    url: clipped.toDataURL(),
    bounds: [
      [south, west],
      [north, east],
    ],
  };
}
