import { Component } from '@angular/core';

/** Le idee che girano in testa ad Archie mentre studia: solo parole, i numeri li calcola il codice */
export const IDEAS = ['xG', 'forma', 'gol fatti', 'in casa', 'Over', '1X2', 'assenti', 'quote', 'tiri', 'riposo', 'precedenti', 'difesa'];

/** Quanto dura lo studio a schermo (ms). Zero se l'utente ha chiesto meno animazioni o il browser non le sa dire. */
export function studyTime(): number {
  const calm = typeof matchMedia !== 'function' || matchMedia('(prefers-reduced-motion: reduce)').matches;
  return calm ? 0 : 2600;
}

/** Archie che studia: il gufo al centro e le idee che gli escono dalla testa. */
@Component({
  selector: 'ab-archie-study',
  template: `
    <div class="study" role="status">
      <div class="head">
        @for (idea of ideas; track idea; let i = $index) {
          <span class="idea" [style.--i]="i" aria-hidden="true">{{ idea }}</span>
        }
        <img src="archie.svg" width="112" height="112" alt="" />
      </div>
      <p>Archie sta studiando le partite…</p>
    </div>
  `,
  styles: `
    .study { display: grid; justify-items: center; gap: 10px; padding: 18px 0 8px; overflow: hidden; }
    .head { position: relative; display: grid; place-items: end center; width: 100%; height: 230px; }
    img { position: relative; z-index: 1; border-radius: 24px; animation: nod 1.3s ease-in-out infinite; filter: drop-shadow(0 0 18px var(--neon-soft)); }
    .idea {
      --dx: calc((var(--i) - 5.5) * 24px);
      position: absolute; bottom: 96px; left: 50%;
      padding: 3px 9px; border: 1px solid var(--neon-soft); border-radius: 999px;
      font: 600 11px var(--mono); letter-spacing: 0.06em; text-transform: uppercase; white-space: nowrap;
      color: var(--neon); background: var(--glass); text-shadow: 0 0 8px var(--neon);
      opacity: 0; animation: idea 2.4s ease-out infinite; animation-delay: calc(var(--i) * 0.2s);
    }
    .idea:nth-child(odd) { --lift: -118px; }
    .idea:nth-child(even) { --lift: -84px; }
    p { margin: 0; font: 600 12px var(--mono); letter-spacing: 0.12em; text-transform: uppercase; color: var(--neon-soft); }
    @keyframes idea {
      0% { opacity: 0; transform: translate(-50%, 0) scale(0.6); }
      25% { opacity: 1; }
      70% { opacity: 1; }
      100% { opacity: 0; transform: translate(calc(-50% + var(--dx)), var(--lift)) scale(1); }
    }
    @keyframes nod { 50% { transform: translateY(-5px) rotate(-3deg); } }
    @media (prefers-reduced-motion: reduce) {
      img { animation: none; }
      .idea { display: none; }
    }
  `,
})
export class ArchieStudy {
  protected readonly ideas = IDEAS;
}
