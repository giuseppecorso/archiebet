import { Component } from '@angular/core';
import { Archie3d } from './owl3d/archie-3d';

/** Le idee che girano in testa ad Archie mentre studia: solo parole, i numeri li calcola il codice */
export const IDEAS = ['xG', 'forma', 'assenti', 'in casa', 'tiri', 'quote'];

/** Quanto dura lo studio a schermo (ms). Zero se l'utente ha chiesto meno animazioni o il browser non le sa dire. */
export function studyTime(): number {
  const calm = typeof matchMedia !== 'function' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  return calm ? 0 : 5000;
}

/** La scena dello studio (D184, D193): Archie in 3D pensa con mille idee attorno, poi la multipla si scrive sulla lavagna. */
@Component({
  selector: 'ab-archie-study',
  imports: [Archie3d],
  template: `
    <div class="scene" role="status">
      <div class="owl">
        @for (idea of ideas; track idea; let i = $index) {
          <span class="idea" [style.--i]="i" aria-hidden="true">{{ idea }}</span>
        }
        <span class="bulb" aria-hidden="true">!</span>
        <ab-archie-3d class="owl3d" />
      </div>
      <div class="board" aria-hidden="true">
        <span class="board-title">Lavagna di Archie</span>
        @for (row of rows; track row) {
          <div class="row" [style.--r]="row">
            <svg viewBox="0 0 140 20" preserveAspectRatio="none"><path d="M4 12 q8 -10 16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0 t16 0" /></svg>
            <span class="tick">✓</span>
          </div>
        }
        <span class="ready">Multipla pronta</span>
      </div>
    </div>
    <p class="caption">Archie sta studiando le partite…</p>
  `,
  styles: `
    :host { display: block; padding: 8px 0; }
    .scene { display: flex; align-items: flex-end; gap: 4%; min-height: 230px; padding-top: 70px; }
    .owl { position: relative; flex: 0 0 34%; max-width: 170px; }
    .owl3d { width: 100%; aspect-ratio: 1; }
    .idea {
      position: absolute; left: 50%; top: 10%;
      padding: 3px 9px; border: 1px solid var(--line-strong); border-radius: 999px;
      font: 600 11px var(--mono); letter-spacing: 0.05em; text-transform: uppercase; white-space: nowrap;
      color: var(--text); background: var(--panel-head);
      opacity: 0; animation: idea 1.5s ease-out both; animation-delay: calc(0.15s + var(--i) * 0.26s);
    }
    .idea:nth-child(odd) { --dx: -70px; } .idea:nth-child(even) { --dx: 40px; }
    .idea:nth-child(3n) { --dy: -96px; } .idea:nth-child(3n + 1) { --dy: -70px; } .idea:nth-child(3n + 2) { --dy: -54px; }
    .bulb {
      position: absolute; left: 52%; top: -18%;
      display: grid; place-items: center; width: 34px; height: 34px; border-radius: 50%;
      font: 700 22px var(--font-title); color: #3d1d07; background: #ffc94a;
      opacity: 0; animation: bulb 0.7s ease-out 1.65s both;
    }
    .board {
      position: relative; flex: 1; display: grid; gap: 8px; align-content: start;
      min-height: 190px; padding: 12px 14px; border: 2px solid var(--accent); border-radius: 12px;
      background: linear-gradient(var(--line-row) 1px, transparent 1px) 0 0 / 100% 24px, #10141d;
    }
    .board-title { font: 600 11px var(--mono); letter-spacing: 0.14em; text-transform: uppercase; color: var(--accent); }
    .row { display: flex; align-items: center; gap: 8px; }
    .row svg { flex: 1; height: 18px; clip-path: inset(0 100% 0 0); animation: write 0.45s linear forwards; animation-delay: calc(2.3s + var(--r) * 0.5s); }
    .row path { fill: none; stroke: var(--text-2); stroke-width: 2.4; stroke-linecap: round; vector-effect: non-scaling-stroke; }
    .tick { color: var(--amber); font-weight: 800; opacity: 0; animation: show 0.2s ease-out forwards; animation-delay: calc(2.75s + var(--r) * 0.5s); }
    .ready {
      justify-self: center; margin-top: 4px; padding: 3px 12px; border: 2px solid var(--amber); border-radius: 6px;
      font: 700 15px var(--font-title); letter-spacing: 0.1em; text-transform: uppercase; color: var(--amber);
      opacity: 0; animation: stamp 0.35s cubic-bezier(0.2, 1.6, 0.4, 1) 4.45s forwards;
    }
    .caption { margin: 8px 0 0; text-align: center; font: 600 12px var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--accent); }
    @keyframes idea {
      0% { opacity: 0; transform: translate(-50%, 0) scale(0.5); }
      30%, 75% { opacity: 1; }
      100% { opacity: 0; transform: translate(calc(-50% + var(--dx)), var(--dy)) scale(1); }
    }
    @keyframes bulb { 0% { opacity: 0; transform: scale(0.3); } 40% { opacity: 1; transform: scale(1.25); } 80% { opacity: 1; transform: scale(1); } 100% { opacity: 0; } }
    @keyframes write { to { clip-path: inset(0 0 0 0); } }
    @keyframes show { to { opacity: 1; } }
    @keyframes stamp { from { opacity: 0; transform: scale(1.8) rotate(-8deg); } to { opacity: 1; transform: scale(1) rotate(-4deg); } }
    @media (max-width: 480px) { .idea { font-size: 10px; } }
    @media (prefers-reduced-motion: reduce) {
      .idea, .bulb { display: none; }
      .row svg { animation: none; clip-path: none; }
      .tick, .ready { animation: none; opacity: 1; }
    }
  `,
})
export class ArchieStudy {
  protected readonly ideas = IDEAS;
  protected readonly rows = [0, 1, 2, 3];
}
