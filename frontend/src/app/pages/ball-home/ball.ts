/**
 * Il pallone classico (icosaedro troncato): 12 toppe nere a cinque lati e 20 bianche a sei.
 * Qui solo i conti, senza grafica: così si possono provare con i test.
 */
import { DailyLeg, DailySlip } from '../../core/daily';

export type Vec3 = readonly [number, number, number];

const PHI = (1 + Math.sqrt(5)) / 2;
/** Distanza dal centro delle toppe a 5 e a 6 lati, con lato 1: quelle a 5 lati sono un filo più lontane. */
const PENTAGON_DISTANCE = 0.5 * Math.sqrt((125 + 41 * Math.sqrt(5)) / 10);
const HEXAGON_DISTANCE = 0.5 * Math.sqrt(1.5 * (7 + 3 * Math.sqrt(5)));
/** Di quanto pesa di più una toppa bianca nel confronto (vedi faceAt). */
export const HEXAGON_WEIGHT = PENTAGON_DISTANCE / HEXAGON_DISTANCE;

export const dot = (a: Vec3, b: Vec3): number => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];

export function unit(v: Vec3): Vec3 {
  const n = Math.hypot(v[0], v[1], v[2]);
  return [v[0] / n, v[1] / n, v[2] / n];
}

function pentagonCenters(): Vec3[] {
  const out: Vec3[] = [];
  for (const a of [-1, 1]) {
    for (const b of [-PHI, PHI]) {
      out.push(unit([0, a, b]), unit([a, b, 0]), unit([b, 0, a]));
    }
  }
  return out;
}

function hexagonCenters(pentagons: Vec3[]): Vec3[] {
  const near = 2 / Math.hypot(1, PHI); // distanza fra due toppe nere vicine, sulla sfera di raggio 1
  const close = (a: Vec3, b: Vec3) => Math.abs(Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]) - near) < 1e-6;
  const out: Vec3[] = [];
  for (let i = 0; i < 12; i++) {
    for (let j = i + 1; j < 12; j++) {
      for (let k = j + 1; k < 12; k++) {
        const [a, b, c] = [pentagons[i], pentagons[j], pentagons[k]];
        if (close(a, b) && close(b, c) && close(a, c)) out.push(unit([a[0] + b[0] + c[0], a[1] + b[1] + c[1], a[2] + b[2] + c[2]]));
      }
    }
  }
  return out;
}

/** Centri delle 12 toppe nere, sulla sfera di raggio 1. */
export const PENTAGONS: readonly Vec3[] = pentagonCenters();
/** Centri delle 20 toppe bianche. */
export const HEXAGONS: readonly Vec3[] = hexagonCenters([...PENTAGONS]);
/** Tutte le 32 toppe: prima le nere. */
export const FACES: readonly Vec3[] = [...PENTAGONS, ...HEXAGONS];

/**
 * Su quale toppa cade un punto del pallone. Le toppe sono facce piane: vince quella che il raggio dal centro incontra per prima.
 * Da 0 a 11 è una toppa nera (una voce del menù), da 12 a 31 una bianca.
 */
export function faceAt(point: Vec3): number {
  const p = unit(point);
  let best = 0;
  let score = -Infinity;
  FACES.forEach((center, i) => {
    const s = dot(p, center) * (i < 12 ? 1 : HEXAGON_WEIGHT);
    if (s > score) [score, best] = [s, i];
  });
  return best;
}

/** La voce del menù toccata, oppure -1 se il dito è su una toppa bianca. */
export function patchAt(point: Vec3): number {
  const face = faceAt(point);
  return face < 12 ? face : -1;
}

export interface BallEntry {
  label: string;
  link: string;
  query?: Record<string, string>;
}

/** Una voce per ogni toppa nera: sono 12, come le toppe. */
export const BALL_MENU: readonly BallEntry[] = [
  { label: 'Partite', link: '/partite' },
  { label: 'Diretta', link: '/partite', query: { stato: 'live' } },
  { label: 'Daily', link: '/pronostici' },
  { label: 'Multipla', link: '/pronostici', query: { tab: 'multipla' } },
  { label: 'Occasioni', link: '/pronostici', query: { tab: 'occasioni' } },
  { label: 'Schedine', link: '/schedine' },
  { label: 'Statistiche', link: '/statistiche' },
  { label: 'Campionati', link: '/laboratorio/campionati' },
  { label: 'Squadre', link: '/laboratorio/squadre' },
  { label: 'Impara', link: '/laboratorio/impara' },
  { label: 'Simulatore', link: '/simulatore' },
  { label: 'Profilo', link: '/profilo' },
];

/** Lo stesso pronostico può stare in più schedine: si conta una volta sola. */
export const legKey = (leg: DailyLeg): string => `${leg.match_id}|${leg.market}|${leg.selection}`;

/** I pronostici della bacheca, senza doppioni. */
export function uniqueLegs(board: readonly DailySlip[]): DailyLeg[] {
  const seen = new Map<string, DailyLeg>();
  for (const slip of board) for (const leg of slip.legs) if (!seen.has(legKey(leg))) seen.set(legKey(leg), leg);
  return [...seen.values()];
}

/** I pronostici presi che non erano ancora stati festeggiati. */
export function freshWins(celebrated: ReadonlySet<string>, legs: readonly DailyLeg[]): DailyLeg[] {
  return legs.filter((leg) => leg.status === 'won' && !celebrated.has(legKey(leg)));
}
