/** Il volo di Archie attorno al pallone (D188): un'ellisse, davanti al pallone nella metà bassa e dietro in quella alta,
 *  con una scia d'aria che sfuma e qualche piuma che cade. Calcoli puri qui sopra, il disegno nella classe Flight. */

export const PERIOD_MS = 14_000;
export const TRAIL_MS = 2_400;
const RX = 0.41; // semiasse orizzontale, in frazioni del lato corto della scena
const RY = 0.194;
const CY = -0.037;

export interface OrbitPoint {
  /** posizione in frazioni del lato corto, rispetto al centro della scena */
  x: number;
  y: number;
  /** grandezza: più piccolo dietro il pallone, più grande davanti */
  scale: number;
  front: boolean;
  /** inclinazione nel verso del volo, in gradi */
  tilt: number;
}

export function orbitAt(ms: number): OrbitPoint {
  const a = ((ms % PERIOD_MS) / PERIOD_MS) * 2 * Math.PI;
  const sin = Math.sin(a);
  const vx = -Math.sin(a); // verso del moto orizzontale (derivata di cos)
  return { x: RX * Math.cos(a), y: CY + RY * sin, scale: 0.8 + 0.25 * sin, front: sin > 0, tilt: 10 * vx };
}

export interface TrailPoint {
  x: number; // pixel
  y: number;
  t: number; // ms
  scale: number;
  front: boolean;
}

export interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  opacity: number;
  width: number;
  front: boolean;
}

/** I tratti della scia: più vecchi = più trasparenti e sottili; quelli scaduti spariscono. */
export function trailSegments(points: readonly TrailPoint[], now: number): Segment[] {
  const out: Segment[] = [];
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1];
    const b = points[i];
    const life = 1 - (now - a.t) / TRAIL_MS;
    if (life <= 0) continue;
    out.push({
      x1: a.x, y1: a.y, x2: b.x, y2: b.y,
      opacity: 0.32 * life ** 1.3,
      width: (3 + 11 * life) * b.scale,
      front: a.front && b.front,
    }); // prettier-ignore
  }
  return out;
}

/** Tieni solo i punti ancora visibili nella scia. */
export function prune(points: TrailPoint[], now: number): TrailPoint[] {
  return points.filter((p) => now - p.t < TRAIL_MS);
}

const SVG = 'http://www.w3.org/2000/svg';
const POOL = 180;
const MAX_FEATHERS = 8;

export interface FlightParts {
  stage: HTMLElement;
  owl: HTMLElement;
  trail: { back: SVGSVGElement; front: SVGSVGElement };
  feathers: { back: HTMLElement; front: HTMLElement };
}

/** Muove Archie a ogni fotogramma, fuori dal ciclo di Angular (nessun ricalcolo della pagina). */
export class Flight {
  private frame = 0;
  private points: TrailPoint[] = [];
  private nextFeather = 0;
  private readonly lines: { back: SVGLineElement[]; front: SVGLineElement[] };
  private readonly start = performance.now();

  constructor(private readonly parts: FlightParts) {
    const pool = (svg: SVGSVGElement) =>
      Array.from({ length: POOL }, () => {
        const line = document.createElementNS(SVG, 'line');
        line.setAttribute('stroke-linecap', 'round');
        svg.appendChild(line);
        return line;
      });
    this.lines = { back: pool(parts.trail.back), front: pool(parts.trail.front) };
    this.frame = requestAnimationFrame((t) => this.tick(t));
  }

  destroy(): void {
    cancelAnimationFrame(this.frame);
  }

  private tick(now: number): void {
    const { stage, owl } = this.parts;
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    const u = Math.min(w, h);
    const o = orbitAt(now - this.start);
    const x = w / 2 + o.x * u;
    const y = h / 2 + o.y * u;
    const size = owl.offsetWidth;
    owl.style.transform = `translate(${x - size / 2}px, ${y - size / 2}px) scale(${o.scale}) rotate(${o.tilt}deg)`;
    owl.style.zIndex = o.front ? '3' : '0';

    // la scia parte dal corpo, un po' sotto il centro del disegno
    this.points.push({ x, y: y + size * 0.12 * o.scale, t: now, scale: o.scale, front: o.front });
    this.points = prune(this.points, now);
    this.draw(trailSegments(this.points, now));

    if (now >= this.nextFeather) {
      this.drop(x, y + size * 0.2 * o.scale, o);
      this.nextFeather = now + 700 + Math.random() * 900;
    }
    this.frame = requestAnimationFrame((t) => this.tick(t));
  }

  private draw(segments: Segment[]): void {
    const used = { back: 0, front: 0 };
    for (const s of segments) {
      const side = s.front ? 'front' : 'back';
      const line = this.lines[side][used[side]++];
      if (!line) continue;
      line.setAttribute('x1', String(s.x1));
      line.setAttribute('y1', String(s.y1));
      line.setAttribute('x2', String(s.x2));
      line.setAttribute('y2', String(s.y2));
      line.setAttribute('stroke-width', s.width.toFixed(1));
      line.setAttribute('stroke-opacity', s.opacity.toFixed(3));
    }
    for (const side of ['back', 'front'] as const) {
      for (let i = used[side]; i < POOL; i++) this.lines[side][i].setAttribute('stroke-opacity', '0');
    }
  }

  private drop(x: number, y: number, o: OrbitPoint): void {
    const box = o.front ? this.parts.feathers.front : this.parts.feathers.back;
    if (box.childElementCount >= MAX_FEATHERS) return;
    const f = document.createElement('i');
    f.className = 'feather';
    f.style.left = `${x}px`;
    f.style.top = `${y}px`;
    f.style.setProperty('--s', o.scale.toFixed(2));
    f.style.setProperty('--dx', `${(Math.random() * 2 - 1) * 40}px`);
    f.style.setProperty('--r', `${(Math.random() * 2 - 1) * 160}deg`);
    f.addEventListener('animationend', () => f.remove(), { once: true });
    box.appendChild(f);
  }
}

/** Il volo parte solo se il browser sa animare e l'utente non ha chiesto meno movimento. */
export function canFly(): boolean {
  return (
    typeof requestAnimationFrame === 'function' &&
    typeof matchMedia === 'function' &&
    !matchMedia('(prefers-reduced-motion: reduce)').matches
  );
}
