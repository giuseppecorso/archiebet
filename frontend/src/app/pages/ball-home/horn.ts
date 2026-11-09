/** Trombe da stadio fatte con il sintetizzatore del browser (Web Audio): nessun file audio da scaricare. */

/** Tre squilli: due corti e uno lungo. [inizio in secondi, durata] */
export const BLASTS: readonly (readonly [number, number])[] = [
  [0, 0.2],
  [0.27, 0.2],
  [0.54, 0.85],
];
const NOTES = [233.08, 234.6, 349.23]; // si bemolle, lo stesso un filo stonato (più trombe insieme) e il fa sopra

export function playHorns(ctx: AudioContext, volume = 0.22): void {
  const filter = ctx.createBiquadFilter();
  filter.type = 'lowpass';
  filter.frequency.value = 1500;
  filter.connect(ctx.destination);
  for (const [start, length] of BLASTS) {
    const t = ctx.currentTime + 0.03 + start;
    const gain = ctx.createGain();
    gain.gain.setValueAtTime(0, t);
    gain.gain.linearRampToValueAtTime(volume, t + 0.03);
    gain.gain.setValueAtTime(volume, t + length - 0.08);
    gain.gain.linearRampToValueAtTime(0, t + length);
    gain.connect(filter);
    for (const note of NOTES) {
      const osc = ctx.createOscillator();
      osc.type = 'sawtooth';
      osc.frequency.value = note;
      osc.connect(gain);
      osc.start(t);
      osc.stop(t + length + 0.02);
    }
  }
}
