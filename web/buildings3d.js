// 3D buildings drawn with three.js inside MapLibre (a custom layer).
//
// Every OSM building or building:part is drawn from the same numbers the Python
// shadow model uses: height, min_height (parts on columns), roof shape (dome,
// pyramid) and the EXPO sphere. Walls get windows per 3.2 m floor, the light
// comes from the real sun position, and windows light up at night.

import * as THREE from 'three';

const FLOOR = 3.2;                 // metres per storey, as in config.py
const SLICES = 12;                 // dome / pyramid roof smoothness
const WHITE = new THREE.Color('#ffffff');

const GLASS_KINDS = new Set(['office', 'commercial', 'retail', 'university', 'college', 'public', 'government',
  'hotel', 'civic', 'train_station', 'transportation', 'stadium', 'sports_centre', 'sports_hall', 'mall']);
const PLAIN_KINDS = new Set(['garage', 'garages', 'shed', 'roof', 'service', 'industrial', 'warehouse',
  'construction', 'hut', 'kiosk', 'transformer_tower', 'triumphal_arch', 'carport', 'greenhouse', 'bunker',
  'ruins', 'container', 'storage_tank', 'toilets']);
const WALL_COLOURS = {
  apartments: '#f7f3ec', residential: '#f7f3ec', dormitory: '#f7f3ec', house: '#f6ebdc', detached: '#f6ebdc',
  school: '#f4ece2', kindergarten: '#f6e9da', construction: '#eee3cc', industrial: '#e6e3dd',
};

// ------------------------------------------------------------------ textures

function canvasTexture(width, height, draw, srgb = true) {
  const canvas = document.createElement('canvas');
  canvas.width = width; canvas.height = height;
  draw(canvas.getContext('2d'), width, height);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
  texture.anisotropy = 8;
  if (srgb) texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

// One facade bay: 4 m wide, one 3.2 m floor tall. v = 0 is the floor line.
const facadeWindow = (ctx, w, h, fill) => {
  ctx.fillStyle = fill;
  ctx.fillRect(w * 0.26, h * 0.3, w * 0.48, h * 0.42);
};
const facadeMap = () => canvasTexture(64, 64, (ctx, w, h) => {
  ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, w, h);
  facadeWindow(ctx, w, h, '#aebdd0');
});
const facadeGlow = () => canvasTexture(64, 64, (ctx, w, h) => {
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
  facadeWindow(ctx, w, h, '#fff');
});

// A curtain wall: glass panes between thin mullions, a slab band at every floor.
const glassMap = () => canvasTexture(64, 64, (ctx, w, h) => {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#e8f0fa'); g.addColorStop(1, '#c3d4ea');
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w * 0.05, h);                 // mullion
  ctx.fillRect(0, h * 0.9, w, h * 0.1);            // floor slab (canvas y is flipped vs v)
});
const glassGlow = () => canvasTexture(64, 64, (ctx, w, h) => {
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#fff'; ctx.fillRect(w * 0.08, h * 0.1, w * 0.84, h * 0.75);
});
// The sphere: a light blue glass ball with a white grid of panels.
const sphereMap = () => canvasTexture(1024, 512, (ctx, w, h) => {
  const g = ctx.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, '#e6eef9'); g.addColorStop(1, '#9fb8dc');
  ctx.fillStyle = g; ctx.fillRect(0, 0, w, h);
  ctx.strokeStyle = 'rgba(255,255,255,0.95)'; ctx.lineWidth = 3;
  for (let x = 0; x <= w; x += w / 36) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke(); }
  for (let y = 0; y <= h; y += h / 18) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke(); }
});

// ------------------------------------------------------------------ geometry

class Bucket {
  constructor() { this.pos = []; this.nor = []; this.uv = []; this.col = []; this.tri = []; }

  triangle(a, b, c, n, ua, ub, uc, colour, feature) {
    this.pos.push(...a, ...b, ...c);
    this.nor.push(...n, ...n, ...n);
    this.uv.push(...ua, ...ub, ...uc);
    for (let i = 0; i < 3; i++) this.col.push(colour.r, colour.g, colour.b);
    this.tri.push(feature);
  }

  quad(a0, b0, b1, a1, n, uvs, colour, feature) {
    this.triangle(a0, b0, b1, n, uvs[0], uvs[1], uvs[2], colour, feature);
    this.triangle(a0, b1, a1, n, uvs[0], uvs[2], uvs[3], colour, feature);
  }

  mesh(material) {
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    geometry.setAttribute('normal', new THREE.Float32BufferAttribute(this.nor, 3));
    geometry.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    geometry.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    const mesh = new THREE.Mesh(geometry, material);
    mesh.userData.tri = Int32Array.from(this.tri);
    mesh.matrixAutoUpdate = false;
    return mesh;
  }
}

const signedArea = (ring) => {
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const p = ring[i], q = ring[(i + 1) % ring.length];
    a += p[0] * q[1] - q[0] * p[1];
  }
  return a / 2;
};

function cleanRing(points, counterClockwise) {
  const ring = [];
  for (const p of points) {
    const last = ring[ring.length - 1];
    if (!last || Math.hypot(p[0] - last[0], p[1] - last[1]) > 0.05) ring.push(p);
  }
  if (ring.length > 1 && Math.hypot(ring[0][0] - ring.at(-1)[0], ring[0][1] - ring.at(-1)[1]) < 0.05) ring.pop();
  if (ring.length < 3) return null;
  if ((signedArea(ring) > 0) !== counterClockwise) ring.reverse();
  return ring;
}

const cross = (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const sub = (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const unit = (v) => { const l = Math.hypot(...v) || 1; return [v[0] / l, v[1] / l, v[2] / l]; };

// Walls of one ring from z0 to z1. Exterior rings run counter-clockwise and holes
// clockwise, so (dy, -dx) always points out of the building.
function walls(bucket, ring, z0, z1, colour, feature, bay) {
  let along = 0;
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length];
    const dx = b[0] - a[0], dy = b[1] - a[1], len = Math.hypot(dx, dy);
    const u0 = along / bay, u1 = (along + len) / bay;
    along += len;
    bucket.quad([a[0], a[1], z0], [b[0], b[1], z0], [b[0], b[1], z1], [a[0], a[1], z1], [dy / len, -dx / len, 0],
      [[u0, z0 / FLOOR], [u1, z0 / FLOOR], [u1, z1 / FLOOR], [u0, z1 / FLOOR]], colour, feature);
  }
}

// A flat cap (roof or underside) with holes, facing up or down.
function cap(bucket, outer, holes, z, up, colour, feature) {
  const contour = outer.map((p) => new THREE.Vector2(p[0], p[1]));
  const holeVectors = holes.map((h) => h.map((p) => new THREE.Vector2(p[0], p[1])));
  const all = outer.concat(...holes);
  const n = [0, 0, up ? 1 : -1];
  for (const [i, j, k] of THREE.ShapeUtils.triangulateShape(contour, holeVectors)) {
    let a = all[i], b = all[j], c = all[k];
    const turn = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    if ((turn > 0) !== up) [b, c] = [c, b];
    bucket.triangle([a[0], a[1], z], [b[0], b[1], z], [c[0], c[1], z], n, [0, 0], [0, 0], [0, 0], colour, feature);
  }
}

// A dome or a pyramid on top of a ring: the ring shrinks towards the centre as it rises.
function curvedRoof(bucket, ring, centre, base, roofHeight, shape, colour, feature) {
  const level = (i) => {
    const t = i / SLICES;
    const angle = t * Math.PI / 2;
    const factor = shape === 'dome' ? Math.cos(angle) : 1 - t;
    const z = base + roofHeight * (shape === 'dome' ? Math.sin(angle) : t);
    return ring.map((p) => [centre[0] + (p[0] - centre[0]) * factor, centre[1] + (p[1] - centre[1]) * factor, z]);
  };
  let lower = level(0);
  for (let i = 1; i <= SLICES; i++) {
    const upper = level(i);
    for (let k = 0; k < ring.length; k++) {
      const m = (k + 1) % ring.length;
      const n = unit(cross(sub(lower[m], lower[k]), sub(upper[k], lower[k])));
      bucket.quad(lower[k], lower[m], upper[m], upper[k], n, [[0, 0], [0, 0], [0, 0], [0, 0]], colour, feature);
    }
    lower = upper;
  }
}

// Building outlines: roof edge, base edge, and the vertical corners.
function outlines(lines, ring, z0, z1) {
  for (let i = 0; i < ring.length; i++) {
    const a = ring[i], b = ring[(i + 1) % ring.length], prev = ring[(i - 1 + ring.length) % ring.length];
    lines.push(a[0], a[1], z1, b[0], b[1], z1);
    if (z0 > 0.3) lines.push(a[0], a[1], z0, b[0], b[1], z0);
    const turn = Math.abs(Math.atan2(b[1] - a[1], b[0] - a[0]) - Math.atan2(a[1] - prev[1], a[0] - prev[0]));
    const corner = Math.min(turn, 2 * Math.PI - turn);
    if (corner > 0.6) lines.push(a[0], a[1], z0, a[0], a[1], z1);
  }
}

function wallColour(p) {
  if (p.colour) {
    const c = new THREE.Color();
    try { c.setStyle(p.colour); return c.lerp(WHITE, 0.4); } catch { /* not a colour */ }
  }
  if (isGlass(p)) return new THREE.Color('#d5e3f4');
  return new THREE.Color(WALL_COLOURS[p.kind] || '#f3f1ed');
}

function roofColour(p) {
  if (p.roof_colour) {
    const c = new THREE.Color();
    try { c.setStyle(p.roof_colour); return c.lerp(WHITE, 0.25); } catch { /* not a colour */ }
  }
  return new THREE.Color(isGlass(p) ? '#9aa2af' : '#a9acb2');
}

const isGlass = (p) => p.material === 'glass' || GLASS_KINDS.has(p.kind);

// ------------------------------------------------------------------ the layer

export class Buildings3D {
  constructor(maplibregl, geojson, originLngLat, trees = null) {
    this.id = 'buildings-3d';
    this.type = 'custom';
    this.renderingMode = '3d';
    this.maplibregl = maplibregl;
    this.features = geojson.features;
    this.originLngLat = originLngLat;
    this.trees = trees;
    this.visible = true;
    this.raycaster = new THREE.Raycaster();
  }

  toLocal([lon, lat]) {
    const m = this.maplibregl.MercatorCoordinate.fromLngLat([lon, lat], 0);
    return [(m.x - this.origin.x) / this.scale, -(m.y - this.origin.y) / this.scale];
  }

  onAdd(map, gl) {
    this.map = map;
    this.origin = this.maplibregl.MercatorCoordinate.fromLngLat(this.originLngLat, 0);
    this.scale = this.origin.meterInMercatorCoordinateUnits();
    // local metres (x east, y north, z up) -> MapLibre's mercator units (y points south)
    this.modelMatrix = new THREE.Matrix4()
      .makeTranslation(this.origin.x, this.origin.y, this.origin.z)
      .scale(new THREE.Vector3(this.scale, -this.scale, this.scale));
    this.camera = new THREE.Camera();
    this.scene = new THREE.Scene();
    this.hemi = new THREE.HemisphereLight(0xffffff, 0xe6e0d4, 2.3);
    this.sun = new THREE.DirectionalLight(0xfff3e0, 1.9);
    this.scene.add(this.hemi, this.sun, this.sun.target);
    this.build();
    this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true });
    this.renderer.autoClear = false;
  }

  build() {
    const facade = new Bucket(), glass = new Bucket(), plain = new Bucket(), roofs = new Bucket();
    const lines = [];
    const spheres = [];
    this.features.forEach((feature, index) => {
      const p = feature.properties;
      const z0 = p.min_height || 0, z1 = p.height;
      const polygons = feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
      if (p.shape === 'sphere' && p.r) { spheres.push({ index, p }); return; }
      const colour = wallColour(p), top = roofColour(p);
      const bucket = PLAIN_KINDS.has(p.kind) ? plain : isGlass(p) ? glass : facade;
      const bay = isGlass(p) ? 3 : 4;
      const roof = p.shape === 'dome' || p.shape === 'pyramidal' ? Math.min(p.roof_height || 0, z1 - z0) : 0;
      const wallTop = z1 - roof;
      for (const rings of polygons) {
        const outer = cleanRing(rings[0].map((c) => this.toLocal(c)), true);
        if (!outer) continue;
        const holes = rings.slice(1).map((r) => cleanRing(r.map((c) => this.toLocal(c)), false)).filter(Boolean);
        if (wallTop > z0 + 0.05) {
          for (const ring of [outer, ...holes]) walls(bucket, ring, z0, wallTop, colour, index, bay);
          if (z0 > 0.3) cap(roofs, outer, holes, z0, false, top, index);
          for (const ring of [outer, ...holes]) outlines(lines, ring, z0, wallTop);
        }
        if (roof > 0) {
          curvedRoof(roofs, outer, this.toLocal([p.cx, p.cy]), wallTop, roof, p.shape, top, index);
        } else {
          cap(roofs, outer, holes, wallTop, true, top, index);
        }
      }
    });

    this.facadeGlow = facadeGlow();
    this.glassGlow = glassGlow();
    this.materials = {
      facade: new THREE.MeshLambertMaterial({ vertexColors: true, map: facadeMap(), emissive: 0xffc46b,
        emissiveMap: this.facadeGlow, emissiveIntensity: 0 }),
      glass: new THREE.MeshPhongMaterial({ vertexColors: true, map: glassMap(), emissive: 0xffd99a,
        emissiveMap: this.glassGlow, emissiveIntensity: 0, shininess: 40, specular: 0x3a4a5e }),
      plain: new THREE.MeshLambertMaterial({ vertexColors: true }),
      roof: new THREE.MeshLambertMaterial({ vertexColors: true }),
      sphere: new THREE.MeshPhongMaterial({ map: sphereMap(), shininess: 80, specular: 0x8fa3bd,
        emissive: 0x7fb2ff, emissiveIntensity: 0 }),
    };
    this.pickables = [
      facade.mesh(this.materials.facade), glass.mesh(this.materials.glass),
      plain.mesh(this.materials.plain), roofs.mesh(this.materials.roof),
    ];
    for (const { index, p } of spheres) {
      const [cx, cy] = this.toLocal([p.cx, p.cy]);
      const ball = new THREE.SphereGeometry(p.r, 72, 40).rotateX(Math.PI / 2).translate(cx, cy, p.zc);
      const mesh = new THREE.Mesh(ball, this.materials.sphere);
      mesh.userData.feature = index;
      this.pickables.push(mesh);
      const neckHeight = p.neck_top - (p.min_height || 0);
      if (neckHeight > 0.1) {
        const neck = new THREE.CylinderGeometry(p.neck_r, p.neck_r * 1.15, neckHeight, 48)
          .rotateX(Math.PI / 2).translate(cx, cy, (p.min_height || 0) + neckHeight / 2);
        const neckMesh = new THREE.Mesh(neck, this.materials.glass.clone());
        neckMesh.material.vertexColors = false;
        neckMesh.material.color = new THREE.Color('#c9d9ee');
        neckMesh.userData.feature = index;
        this.pickables.push(neckMesh);
      }
    }
    const edgeGeometry = new THREE.BufferGeometry();
    edgeGeometry.setAttribute('position', new THREE.Float32BufferAttribute(lines, 3));
    this.edges = new THREE.LineSegments(edgeGeometry,
      new THREE.LineBasicMaterial({ color: 0x505a69, transparent: true, opacity: 0.42 }));
    this.scene.add(...this.pickables, this.edges);
    if (this.trees) this.buildTrees(this.trees.points, this.trees.crown_radius_m);
  }

  // Trees as instanced meshes: one trunk and one crown each, crown radius as in the shade model.
  buildTrees(points, radius) {
    const crown = new THREE.IcosahedronGeometry(radius, 1).scale(1, 1, 0.9);
    const trunk = new THREE.CylinderGeometry(0.22, 0.3, 3.2, 6).rotateX(Math.PI / 2);
    const crowns = new THREE.InstancedMesh(crown, new THREE.MeshLambertMaterial({ color: 0xffffff, flatShading: true }), points.length);
    const trunks = new THREE.InstancedMesh(trunk, new THREE.MeshLambertMaterial({ color: 0x8a6f55 }), points.length);
    const matrix = new THREE.Matrix4(), colour = new THREE.Color();
    points.forEach(([lon, lat], i) => {
      const [x, y] = this.toLocal([lon, lat]);
      const size = 0.85 + 0.3 * Math.abs(Math.sin(x * 12.9898 + y * 78.233));   // stable "random" size
      matrix.makeScale(size, size, size).setPosition(x, y, 3.2 + radius * 0.8 * size);
      crowns.setMatrixAt(i, matrix);
      matrix.makeScale(1, 1, size).setPosition(x, y, 1.6 * size);
      trunks.setMatrixAt(i, matrix);
      crowns.setColorAt(i, colour.setHSL(0.27 + 0.05 * Math.sin(x + y), 0.42, 0.42 + 0.08 * Math.cos(x * 0.7)));
    });
    this.scene.add(crowns, trunks);
  }

  // altitude / azimuth in degrees, from the sun formula
  setSun(altitude, azimuth) {
    const alt = THREE.MathUtils.degToRad(Math.max(altitude, 2));
    const az = THREE.MathUtils.degToRad(azimuth);
    this.sun.position.set(Math.sin(az) * Math.cos(alt), Math.cos(az) * Math.cos(alt), Math.sin(alt)).multiplyScalar(1000);
    const day = THREE.MathUtils.clamp((altitude + 4) / 10, 0, 1);       // twilight from -4 to +6 deg
    const warm = THREE.MathUtils.clamp(altitude / 25, 0, 1);            // low sun is orange
    this.sun.intensity = 1.9 * day;
    this.sun.color.set('#ffb070').lerp(new THREE.Color('#fff6ea'), warm);
    this.hemi.intensity = 0.7 + 1.6 * day;
    this.hemi.color.set('#7f95c4').lerp(WHITE, day);
    const night = 1 - day;
    this.materials.facade.emissiveIntensity = 0.85 * night;
    this.materials.glass.emissiveIntensity = 0.7 * night;
    this.materials.sphere.emissiveIntensity = 0.55 * night;
    this.map?.triggerRepaint();
  }

  setVisible(visible) {
    this.visible = visible;
    this.map?.triggerRepaint();
  }

  render(gl, matrix) {
    if (!this.visible) return;
    this.camera.projectionMatrix = new THREE.Matrix4().fromArray(matrix).multiply(this.modelMatrix);
    this.renderer.resetState();
    this.renderer.render(this.scene, this.camera);
  }

  // The building under a screen point, or null.
  pick(x, y) {
    if (!this.visible || !this.camera) return null;
    const canvas = this.map.getCanvas();
    const ndcX = (x / canvas.clientWidth) * 2 - 1, ndcY = -(y / canvas.clientHeight) * 2 + 1;
    const inverse = this.camera.projectionMatrix.clone().invert();
    const near = new THREE.Vector3(ndcX, ndcY, -1).applyMatrix4(inverse);
    const far = new THREE.Vector3(ndcX, ndcY, 1).applyMatrix4(inverse);
    this.raycaster.set(near, far.sub(near).normalize());
    const hit = this.raycaster.intersectObjects(this.pickables, false)[0];
    if (!hit) return null;
    const index = hit.object.userData.feature ?? hit.object.userData.tri[hit.faceIndex];
    return this.features[index]?.properties ?? null;
  }
}
