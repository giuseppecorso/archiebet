/** Il pallone in 3D (three.js): disegno, rotazione con il dito e posizione delle etichette. I conti stanno in ball.ts. */
import {
  AdditiveBlending, BackSide, BufferGeometry, DoubleSide, Float32BufferAttribute, Group, Mesh, PerspectiveCamera, Quaternion,
  Raycaster, Scene, ShaderMaterial, SphereGeometry, Vector2, Vector3, WebGLRenderer,
} from 'three'; // prettier-ignore
import { FACES, HEXAGON_WEIGHT, PENTAGONS, Vec3, patchAt, pentagonCorners, unit } from './ball';

const VERTEX = /* glsl */ `
  varying vec3 vLocal;
  varying vec3 vNormal;
  void main() {
    vLocal = position;
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/* Per ogni punto si cerca la toppa (stessa regola di faceAt). "gap" vale zero sulla cucitura e cresce verso il centro della toppa. */
const FIND_FACE = /* glsl */ `
  uniform vec3 uCenters[32];
  uniform float uHexWeight;
  varying vec3 vLocal;
  varying vec3 vNormal;
  const vec3 NEON = vec3(1.0, 0.6, 0.24); // arancio di Archie (D185)
  float seamGap(out int face) {
    vec3 p = normalize(vLocal);
    float best = -2.0;
    float second = -2.0;
    face = 0;
    for (int i = 0; i < 32; i++) {
      float s = dot(p, uCenters[i]) * (i < 12 ? 1.0 : uHexWeight);
      if (s > best) { second = best; best = s; face = i; }
      else if (s > second) { second = s; }
    }
    return best - second;
  }
`;

/* Il pallone: toppe bianche, cuciture accese. Sotto le toppe nere (che sono pezzi a parte) c'è la luce. */
const BALL_FRAGMENT = /* glsl */ `
  ${FIND_FACE}
  uniform float uTime;
  uniform float uParty;
  void main() {
    int face;
    float gap = seamGap(face);
    float core = 1.0 - smoothstep(0.002, 0.011, gap);
    float pulse = 0.85 + 0.15 * sin(uTime * 2.2) + uParty;
    float glow = exp(-gap * 26.0) * pulse;
    vec3 n = normalize(vNormal);
    float light = 0.3 + 0.7 * max(dot(n, normalize(vec3(-0.45, 0.6, 0.66))), 0.0);
    vec3 color;
    if (face < 12) {
      color = mix(NEON, vec3(1.0, 0.9, 0.8), 0.35); // l'interno del pallone è luce: si vede quando la toppa si solleva
    } else {
      color = vec3(0.86, 0.87, 0.9) * light;
      color = mix(color, NEON, min(glow * 0.35, 1.0));
    }
    color = mix(color, vec3(1.0, 0.82, 0.62), core * 0.7);
    color += NEON * pow(1.0 - max(n.z, 0.0), 2.6) * (0.12 + uParty);
    gl_FragColor = vec4(color, 1.0);
  }
`;

/* La luce che esce dalle fessure: gusci trasparenti sopra il pallone che disegnano solo le cuciture, sempre più deboli salendo. */
const BEAM_FRAGMENT = /* glsl */ `
  ${FIND_FACE}
  uniform float uTime;
  uniform float uParty;
  uniform float uStrength;
  uniform float uWidth;
  void main() {
    int face;
    float gap = seamGap(face);
    float beam = (1.0 - smoothstep(0.0, uWidth, gap)) * uStrength * (0.8 + 0.2 * sin(uTime * 2.2) + 1.5 * uParty);
    gl_FragColor = vec4(NEON * beam * 0.45, beam * 0.45);
  }
`;

/* Alone attorno al pallone: forte sul bordo, si spegne allontanandosi. */
const HALO_FRAGMENT = /* glsl */ `
  varying vec3 vNormal;
  uniform float uParty;
  void main() {
    float a = pow(clamp(abs(normalize(vNormal).z) / 0.62, 0.0, 1.0), 2.4) * (0.25 + uParty);
    gl_FragColor = vec4(vec3(1.0, 0.6, 0.24) * a, a);
  }
`;

const CAP_VERTEX = /* glsl */ `
  attribute float edge;
  varying float vEdge;
  void main() {
    vEdge = edge;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/* Una toppa nera: scura al centro, accesa sul bordo; i fianchi (edge negativo) sono luce piena. */
const CAP_FRAGMENT = /* glsl */ `
  varying float vEdge;
  uniform float uOn;
  uniform float uTime;
  void main() {
    vec3 neon = vec3(1.0, 0.6, 0.24);
    if (vEdge < 0.0) { gl_FragColor = vec4(mix(neon, vec3(1.0), 0.25), 1.0); return; }
    float glow = exp(-vEdge * 6.5) * (0.3 + 0.08 * sin(uTime * 2.2));
    vec3 color = vec3(0.05, 0.06, 0.09) + neon * (glow + uOn * (0.16 + 0.5 * exp(-vEdge * 3.0)));
    color = mix(color, vec3(1.0, 0.82, 0.62), 0.6 * (1.0 - smoothstep(0.015, 0.06, vEdge)));
    gl_FragColor = vec4(color, 1.0);
  }
`;

const DRAG_SPEED = 0.0075; // radianti per pixel
const IDLE_SPIN = 0.0022;
const TAP_PIXELS = 8;
const LIFT = 0.11; // di quanto si solleva la toppa puntata (il pallone ha raggio 1)
const CAP_RINGS = 5;
const BEAMS = [1.012, 1.03, 1.055, 1.085, 1.12, 1.16]; // raggi dei gusci di luce
const FRONT = new Vector3(0, 0, 1);

export interface LabelPlace {
  x: number;
  y: number;
  /** 0 = dietro al pallone, 1 = proprio davanti */
  facing: number;
}

/** La toppa nera come pezzo a parte: una calotta a cinque spicchi, con i fianchi che scendono dentro il pallone. */
function capGeometry(patch: number): BufferGeometry {
  const center = PENTAGONS[patch];
  const corners = pentagonCorners(patch);
  const positions: number[] = [];
  const edges: number[] = [];
  const add = (p: Vec3, radius: number, edge: number) => {
    const q = unit(p);
    positions.push(q[0] * radius, q[1] * radius, q[2] * radius);
    edges.push(edge);
  };
  for (let k = 0; k < 5; k++) {
    const a = corners[k];
    const b = corners[(k + 1) % 5];
    // punto dello spicchio: i = distanza dal centro (0..CAP_RINGS), j = passo lungo il bordo
    const at = (i: number, j: number): Vec3 => [0, 1, 2].map((d) => center[d] + ((a[d] - center[d]) * i + (b[d] - a[d]) * j) / CAP_RINGS) as unknown as Vec3;
    const top = (i: number, j: number) => add(at(i, j), 1.003, 1 - i / CAP_RINGS);
    for (let i = 0; i < CAP_RINGS; i++) {
      for (let j = 0; j <= i; j++) {
        top(i, j), top(i + 1, j), top(i + 1, j + 1);
        if (j < i) top(i, j), top(i + 1, j + 1), top(i, j + 1);
      }
    }
    add(a, 1.003, -1), add(a, 0.86, -1), add(b, 1.003, -1); // fianco
    add(b, 1.003, -1), add(a, 0.86, -1), add(b, 0.86, -1);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3));
  geometry.setAttribute('edge', new Float32BufferAttribute(edges, 1));
  return geometry;
}

export class BallScene {
  private readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(32, 1, 0.1, 20);
  private readonly ball = new Group();
  private readonly sphere: Mesh;
  private readonly caps: Mesh<BufferGeometry, ShaderMaterial>[];
  private readonly materials: ShaderMaterial[] = [];
  private readonly lifts = PENTAGONS.map(() => 0);
  private readonly raycaster = new Raycaster();
  private readonly centers = PENTAGONS.map((c) => new Vector3(...c));
  private frame = 0;
  private size = 0;
  private velocity = { x: IDLE_SPIN, y: 0 };
  private drag: { id: number; x: number; y: number; startX: number; startY: number } | null = null;
  private target: { q: Quaternion; done: () => void } | null = null;
  private hover = -1;
  private active = -1;
  private party = 0;
  private readonly still: boolean;

  constructor(
    private readonly stage: HTMLElement,
    canvas: HTMLCanvasElement,
    private readonly onLabels: (places: LabelPlace[]) => void,
    private readonly onPick: (patch: number) => void,
  ) {
    this.still = matchMedia('(prefers-reduced-motion: reduce)').matches;
    this.renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2)); // oltre 2 il telefono lavora di più senza che si veda

    const faces = { uCenters: { value: FACES.map((c) => new Vector3(...c)) }, uHexWeight: { value: HEXAGON_WEIGHT } };
    const round = new SphereGeometry(1, 64, 48);
    this.sphere = new Mesh(round, this.shader(BALL_FRAGMENT, { ...faces }));
    this.ball.add(this.sphere);

    this.caps = PENTAGONS.map((_, i) => {
      const material = this.shader(CAP_FRAGMENT, { uOn: { value: 0 } }, CAP_VERTEX);
      material.side = DoubleSide;
      return new Mesh(capGeometry(i), material);
    });
    this.ball.add(...this.caps);

    BEAMS.forEach((radius, i) => {
      const material = this.shader(BEAM_FRAGMENT, { ...faces, uStrength: { value: 0.75 * (1 - i / BEAMS.length) }, uWidth: { value: 0.012 + 0.006 * i } });
      this.glowing(material);
      const shell = new Mesh(round, material);
      shell.scale.setScalar(radius);
      this.ball.add(shell);
    });

    const halo = new Mesh(round, this.glowing(this.shader(HALO_FRAGMENT, {})));
    halo.material.side = BackSide;
    halo.scale.setScalar(1.27);
    this.scene.add(halo);

    this.ball.quaternion.setFromAxisAngle(new Vector3(1, 0, 0), 0.35);
    this.scene.add(this.ball);
    this.camera.position.z = 4.95;

    stage.addEventListener('pointerdown', this.down);
    stage.addEventListener('pointermove', this.move);
    stage.addEventListener('pointerup', this.up);
    stage.addEventListener('pointercancel', this.leave);
    stage.addEventListener('pointerleave', this.leave);
    this.resize();
    this.frame = requestAnimationFrame(this.tick);
  }

  /** Porta una toppa davanti e poi avvisa. */
  bringToFront(patch: number, done: () => void): void {
    this.active = patch;
    const now = this.centers[patch].clone().applyQuaternion(this.ball.quaternion);
    this.target = { q: new Quaternion().setFromUnitVectors(now, FRONT).multiply(this.ball.quaternion), done };
    this.velocity = { x: 0, y: 0 };
  }

  /** Festa: il pallone gira forte e si accende. */
  celebrate(): void {
    this.party = 1;
    if (!this.still) this.velocity = { x: 0.32, y: 0.05 };
  }

  resize(): void {
    const size = Math.round(this.stage.clientWidth);
    if (!size || size === this.size) return;
    this.size = size;
    this.renderer.setSize(size, size, false);
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
    this.stage.removeEventListener('pointerdown', this.down);
    this.stage.removeEventListener('pointermove', this.move);
    this.stage.removeEventListener('pointerup', this.up);
    this.stage.removeEventListener('pointercancel', this.leave);
    this.stage.removeEventListener('pointerleave', this.leave);
    this.sphere.geometry.dispose();
    this.caps.forEach((cap) => cap.geometry.dispose());
    this.materials.forEach((m) => m.dispose());
    this.renderer.dispose();
  }

  private shader(fragmentShader: string, uniforms: ShaderMaterial['uniforms'], vertexShader = VERTEX): ShaderMaterial {
    const material = new ShaderMaterial({ vertexShader, fragmentShader, uniforms: { ...uniforms, uTime: { value: 0 }, uParty: { value: 0 } } });
    this.materials.push(material);
    return material;
  }

  /** Luce che si somma a quello che c'è dietro, senza coprirlo. */
  private glowing(material: ShaderMaterial): ShaderMaterial {
    material.transparent = true;
    material.blending = AdditiveBlending;
    material.depthWrite = false;
    return material;
  }

  /** La toppa nera sotto il puntatore, o -1. */
  private patchUnder(e: PointerEvent): number {
    const box = this.stage.getBoundingClientRect();
    const point = new Vector2(((e.clientX - box.left) / box.width) * 2 - 1, 1 - ((e.clientY - box.top) / box.height) * 2);
    this.raycaster.setFromCamera(point, this.camera);
    const hit = this.raycaster.intersectObject(this.sphere)[0];
    if (!hit) return -1;
    const local = this.ball.worldToLocal(hit.point.clone());
    return patchAt([local.x, local.y, local.z]);
  }

  private readonly down = (e: PointerEvent): void => {
    this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY };
    this.stage.setPointerCapture(e.pointerId);
    this.velocity = { x: 0, y: 0 };
    this.target = null;
    this.hover = this.patchUnder(e); // con il dito: la toppa si solleva appena la tocchi
  };

  private readonly move = (e: PointerEvent): void => {
    if (!this.drag || e.pointerId !== this.drag.id) {
      this.hover = this.patchUnder(e); // con il mouse: si solleva la toppa puntata
      this.stage.style.cursor = this.hover >= 0 ? 'pointer' : '';
      return;
    }
    this.velocity = { x: (e.clientX - this.drag.x) * DRAG_SPEED, y: (e.clientY - this.drag.y) * DRAG_SPEED };
    this.rotate(this.velocity.x, this.velocity.y);
    this.drag.x = e.clientX;
    this.drag.y = e.clientY;
    if (Math.hypot(e.clientX - this.drag.startX, e.clientY - this.drag.startY) > TAP_PIXELS) this.hover = -1; // sta girando, non scegliendo
  };

  private readonly up = (e: PointerEvent): void => {
    const drag = this.drag;
    this.drag = null;
    if (e.pointerType !== 'mouse') this.hover = -1;
    if (!drag || Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) > TAP_PIXELS) return;
    const patch = this.patchUnder(e); // un tocco senza trascinare
    if (patch >= 0) this.onPick(patch);
  };

  private readonly leave = (): void => {
    this.drag = null;
    this.hover = -1;
  };

  /** Rotazione attorno agli assi dello schermo: il pallone segue il dito. */
  private rotate(dx: number, dy: number): void {
    const turn = new Quaternion().setFromAxisAngle(new Vector3(0, 1, 0), dx).multiply(new Quaternion().setFromAxisAngle(new Vector3(1, 0, 0), dy));
    this.ball.quaternion.premultiply(turn).normalize();
  }

  private readonly tick = (time: number): void => {
    this.frame = requestAnimationFrame(this.tick);
    if (document.hidden) return;
    this.resize();
    if (this.target) {
      this.ball.quaternion.slerp(this.target.q, 0.16);
      if (this.ball.quaternion.angleTo(this.target.q) < 0.02) {
        const done = this.target.done;
        this.target = null;
        done();
      }
    } else if (!this.drag) {
      this.rotate(this.velocity.x, this.velocity.y);
      // l'inerzia si spegne piano fino al giro lento di riposo; con una toppa puntata il pallone si ferma
      const rest = this.still || this.hover >= 0 ? 0 : IDLE_SPIN;
      this.velocity.x = rest + (this.velocity.x - rest) * 0.95;
      this.velocity.y *= 0.95;
    }
    this.party *= 0.985;
    this.caps.forEach((cap, i) => {
      const wanted = i === this.hover || i === this.active ? 1 : 0;
      this.lifts[i] += (wanted - this.lifts[i]) * 0.2;
      cap.position.copy(this.centers[i]).multiplyScalar(this.lifts[i] * LIFT);
      cap.material.uniforms['uOn'].value = this.lifts[i];
    });
    for (const material of this.materials) {
      material.uniforms['uTime'].value = time / 1000;
      material.uniforms['uParty'].value = this.party;
    }
    this.renderer.render(this.scene, this.camera);
    this.onLabels(this.places());
  };

  private places(): LabelPlace[] {
    return this.centers.map((c, i) => {
      const world = c.clone().applyQuaternion(this.ball.quaternion);
      const facing = Math.min(1, Math.max(0, (world.z - 0.45) / 0.35));
      const screen = world.multiplyScalar(1 + this.lifts[i] * LIFT).project(this.camera);
      return { x: ((screen.x + 1) / 2) * this.size, y: ((1 - screen.y) / 2) * this.size, facing };
    });
  }
}
