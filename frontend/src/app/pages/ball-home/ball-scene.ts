/** Il pallone in 3D (three.js): disegno, rotazione con il dito e posizione delle etichette. I conti stanno in ball.ts. */
import { Mesh, PerspectiveCamera, Quaternion, Raycaster, Scene, ShaderMaterial, SphereGeometry, Vector2, Vector3, WebGLRenderer } from 'three';
import { FACES, HEXAGON_WEIGHT, PENTAGONS, patchAt } from './ball';

const VERTEX = /* glsl */ `
  varying vec3 vLocal;
  varying vec3 vNormal;
  void main() {
    vLocal = position;
    vNormal = normalize(normalMatrix * normal);
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

/* Per ogni punto si cerca la toppa (stessa regola di faceAt): nere le prime 12, cuciture accese di verde. */
const FRAGMENT = /* glsl */ `
  uniform vec3 uCenters[32];
  uniform float uHexWeight;
  uniform int uActive;
  uniform float uTime;
  uniform float uParty;
  varying vec3 vLocal;
  varying vec3 vNormal;
  void main() {
    vec3 p = normalize(vLocal);
    float best = -2.0;
    float second = -2.0;
    int face = 0;
    for (int i = 0; i < 32; i++) {
      float s = dot(p, uCenters[i]) * (i < 12 ? 1.0 : uHexWeight);
      if (s > best) { second = best; best = s; face = i; }
      else if (s > second) { second = s; }
    }
    float gap = best - second;
    float seam = 1.0 - smoothstep(0.004, 0.016, gap);
    float halo = 1.0 - smoothstep(0.0, 0.09, gap);
    vec3 neon = vec3(0.0, 1.0, 0.53);
    vec3 n = normalize(vNormal);
    float light = 0.32 + 0.68 * max(dot(n, normalize(vec3(-0.45, 0.6, 0.66))), 0.0);
    vec3 color;
    if (face < 12) {
      color = vec3(0.012, 0.035, 0.028) + neon * halo * 0.22;
      if (face == uActive) color += vec3(0.0, 0.75, 0.4) * (0.55 + 0.45 * sin(uTime * 7.0));
    } else {
      color = vec3(0.86, 0.93, 0.9) * light;
    }
    color = mix(color, neon * (0.75 + 0.25 * uParty), seam);
    float rim = pow(1.0 - max(n.z, 0.0), 2.6);
    color += neon * rim * (0.55 + uParty);
    gl_FragColor = vec4(color, 1.0);
  }
`;

const RADIUS = 1;
const DRAG_SPEED = 0.0075; // radianti per pixel
const IDLE_SPIN = 0.0022;
const TAP_PIXELS = 8;
const FRONT = new Vector3(0, 0, 1);

export interface LabelPlace {
  x: number;
  y: number;
  /** 0 = dietro al pallone, 1 = proprio davanti */
  facing: number;
}

export class BallScene {
  private readonly renderer: WebGLRenderer;
  private readonly scene = new Scene();
  private readonly camera = new PerspectiveCamera(32, 1, 0.1, 20);
  private readonly material: ShaderMaterial;
  private readonly ball: Mesh;
  private readonly raycaster = new Raycaster();
  private readonly centers = PENTAGONS.map((c) => new Vector3(...c));
  private frame = 0;
  private size = 0;
  private velocity = { x: IDLE_SPIN, y: 0 };
  private drag: { id: number; x: number; y: number; startX: number; startY: number } | null = null;
  private target: { q: Quaternion; done: () => void } | null = null;
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
    this.material = new ShaderMaterial({
      vertexShader: VERTEX,
      fragmentShader: FRAGMENT,
      uniforms: {
        uCenters: { value: FACES.map((c) => new Vector3(...c)) },
        uHexWeight: { value: HEXAGON_WEIGHT },
        uActive: { value: -1 },
        uTime: { value: 0 },
        uParty: { value: 0 },
      },
    });
    this.ball = new Mesh(new SphereGeometry(RADIUS, 64, 48), this.material);
    this.ball.quaternion.setFromAxisAngle(new Vector3(1, 0, 0), 0.35);
    this.scene.add(this.ball);
    this.camera.position.z = 4.3;

    stage.addEventListener('pointerdown', this.down);
    stage.addEventListener('pointermove', this.move);
    stage.addEventListener('pointerup', this.up);
    stage.addEventListener('pointercancel', this.cancel);
    this.resize();
    this.frame = requestAnimationFrame(this.tick);
  }

  /** Porta una toppa davanti e poi avvisa. */
  bringToFront(patch: number, done: () => void): void {
    this.material.uniforms['uActive'].value = patch;
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
    this.stage.removeEventListener('pointercancel', this.cancel);
    this.ball.geometry.dispose();
    this.material.dispose();
    this.renderer.dispose();
  }

  private readonly down = (e: PointerEvent): void => {
    this.drag = { id: e.pointerId, x: e.clientX, y: e.clientY, startX: e.clientX, startY: e.clientY };
    this.stage.setPointerCapture(e.pointerId);
    this.velocity = { x: 0, y: 0 };
    this.target = null;
  };

  private readonly move = (e: PointerEvent): void => {
    if (!this.drag || e.pointerId !== this.drag.id) return;
    this.velocity = { x: (e.clientX - this.drag.x) * DRAG_SPEED, y: (e.clientY - this.drag.y) * DRAG_SPEED };
    this.rotate(this.velocity.x, this.velocity.y);
    this.drag.x = e.clientX;
    this.drag.y = e.clientY;
  };

  private readonly up = (e: PointerEvent): void => {
    const drag = this.drag;
    this.drag = null;
    if (!drag || Math.hypot(e.clientX - drag.startX, e.clientY - drag.startY) > TAP_PIXELS) return;
    // un tocco senza trascinare: quale toppa c'è sotto il dito?
    const box = this.stage.getBoundingClientRect();
    const point = new Vector2(((e.clientX - box.left) / box.width) * 2 - 1, 1 - ((e.clientY - box.top) / box.height) * 2);
    this.raycaster.setFromCamera(point, this.camera);
    const hit = this.raycaster.intersectObject(this.ball)[0];
    if (!hit) return;
    const local = this.ball.worldToLocal(hit.point.clone());
    const patch = patchAt([local.x, local.y, local.z]);
    if (patch >= 0) this.onPick(patch);
  };

  private readonly cancel = (): void => {
    this.drag = null;
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
      // l'inerzia si spegne piano fino al giro lento di riposo
      const rest = this.still ? 0 : IDLE_SPIN;
      this.velocity.x = rest + (this.velocity.x - rest) * 0.95;
      this.velocity.y *= 0.95;
    }
    this.party *= 0.985;
    this.material.uniforms['uTime'].value = time / 1000;
    this.material.uniforms['uParty'].value = this.party;
    this.renderer.render(this.scene, this.camera);
    this.onLabels(this.places());
  };

  private places(): LabelPlace[] {
    return this.centers.map((c) => {
      const world = c.clone().applyQuaternion(this.ball.quaternion);
      const facing = Math.min(1, Math.max(0, (world.z - 0.45) / 0.35));
      const screen = world.multiplyScalar(RADIUS).project(this.camera);
      return { x: ((screen.x + 1) / 2) * this.size, y: ((1 - screen.y) / 2) * this.size, facing };
    });
  }
}
