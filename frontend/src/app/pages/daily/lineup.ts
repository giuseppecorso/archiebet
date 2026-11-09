/** Posto di un giocatore sul campo, in percentuale (0,0 = angolo in alto a sinistra; la porta di Archie è in basso). */
export interface Spot {
  x: number;
  y: number;
}

const ROW_MAX = 4;
const KEEPER_Y = 82;
const BACK_Y = 68;
const FRONT_Y = 14;

/** Quanti giocatori per linea, dalla difesa all'attacco (senza il portiere): linee da 4 al massimo, le più piene dietro. */
export function rowSizes(players: number): number[] {
  const rest = Math.max(0, players - 1);
  if (!rest) return [];
  const rows = Math.ceil(rest / ROW_MAX);
  const base = Math.floor(rest / rows);
  const extra = rest % rows;
  return Array.from({ length: rows }, (_, r) => base + (r < extra ? 1 : 0));
}

/** La formazione per n giocate: la prima è il portiere, le altre si dispongono a linee fino all'attacco. */
export function lineup(players: number): Spot[] {
  if (players <= 0) return [];
  if (players === 1) return [{ x: 50, y: 50 }];
  const spots: Spot[] = [{ x: 50, y: KEEPER_Y }];
  const sizes = rowSizes(players);
  sizes.forEach((size, r) => {
    const y = sizes.length === 1 ? 42 : BACK_Y - (r * (BACK_Y - FRONT_Y)) / (sizes.length - 1);
    for (let i = 0; i < size; i++) spots.push({ x: ((i + 1) / (size + 1)) * 100, y });
  });
  return spots;
}
