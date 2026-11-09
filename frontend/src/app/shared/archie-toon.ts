import { Component, input } from '@angular/core';

/** Cosa sta facendo Archie: fermo, in volo (home) o allo studio davanti alla lavagna (5 secondi) */
export type ToonPose = 'idle' | 'fly' | 'study';

/** Archie a cartone animato (D184): gufo arancio caldo, tondo e brontolone. Le pose sono solo CSS. */
@Component({
  selector: 'ab-archie-toon',
  host: { '[class]': "'pose-' + pose()", 'aria-hidden': 'true' },
  template: `
    <svg viewBox="0 0 200 200" width="100%" height="100%">
      <g class="all">
        <g class="feet" stroke="#ffc94a" stroke-width="5" stroke-linecap="round">
          <path d="M86 162 v10 M94 163 v10 M106 163 v10 M114 162 v10" />
        </g>
        <path class="tuft" d="M66 76 L56 42 L88 64 Z M134 76 L144 42 L112 64 Z" fill="#e8792a" stroke="#3d1d07" stroke-width="4" stroke-linejoin="round" />
        <ellipse cx="100" cy="112" rx="47" ry="55" fill="#ff9a3c" stroke="#3d1d07" stroke-width="4" />
        <ellipse cx="100" cy="134" rx="29" ry="31" fill="#ffe0b8" />
        <path d="M86 126 q6 6 12 0 M102 126 q6 6 12 0 M78 140 q6 6 12 0 M94 140 q6 6 12 0 M110 140 q6 6 12 0 M86 154 q6 6 12 0 M102 154 q6 6 12 0"
              fill="none" stroke="#e8a868" stroke-width="3" stroke-linecap="round" />
        <g class="wing left"><path d="M66 98 C32 92 14 122 22 152 C40 142 56 130 68 122 Z" fill="#e8792a" stroke="#3d1d07" stroke-width="4" stroke-linejoin="round" /></g>
        <g class="wing right">
          <path d="M134 98 C168 92 186 122 178 152 C160 142 144 130 132 122 Z" fill="#e8792a" stroke="#3d1d07" stroke-width="4" stroke-linejoin="round" />
          <path class="pen" d="M176 150 L190 166" stroke="#8c9bff" stroke-width="6" stroke-linecap="round" />
        </g>
        <g class="eyes">
          <circle cx="81" cy="94" r="18" fill="#fff" stroke="#3d1d07" stroke-width="3" />
          <circle cx="119" cy="94" r="18" fill="#fff" stroke="#3d1d07" stroke-width="3" />
          <g class="pupils">
            <circle cx="84" cy="96" r="8" fill="#1b1310" />
            <circle cx="116" cy="96" r="8" fill="#1b1310" />
            <circle cx="81" cy="93" r="2.5" fill="#fff" />
            <circle cx="113" cy="93" r="2.5" fill="#fff" />
          </g>
        </g>
        <path class="brows" d="M100 84 C88 64 70 58 50 60 C58 72 66 78 74 82 C84 77 94 79 100 84 Z M100 84 C112 64 130 58 150 60 C142 72 134 78 126 82 C116 77 106 79 100 84 Z"
              fill="#b5530f" stroke="#3d1d07" stroke-width="3" stroke-linejoin="round" />
        <path d="M100 102 L91 112 L100 124 L109 112 Z" fill="#ffc94a" stroke="#3d1d07" stroke-width="3" stroke-linejoin="round" />
      </g>
    </svg>
  `,
  styles: `
    :host { display: block; }
    svg { display: block; overflow: visible; }
    .all, .wing, .eyes, .pupils, .brows { transform-box: fill-box; }
    .all { transform-origin: 50% 100%; }
    .wing.left { transform-origin: 100% 10%; }
    .wing.right { transform-origin: 0% 10%; }
    .eyes { transform-origin: 50% 50%; animation: blink 4s infinite; }
    .pen { display: none; }

    /* In volo: ali che sbattono e un leggero su e giù */
    :host(.pose-fly) .wing.left { animation: flap-l 0.42s ease-in-out infinite; }
    :host(.pose-fly) .wing.right { animation: flap-r 0.42s ease-in-out infinite; }
    :host(.pose-fly) .all { animation: bob 0.84s ease-in-out infinite; }

    /* Allo studio (5 s): si gratta la testa, gli viene l'idea, si gira e scrive sulla lavagna */
    :host(.pose-study) .pen { display: inline; }
    :host(.pose-study) .wing.right { animation: study-wing 5s ease-in-out forwards; }
    :host(.pose-study) .pupils { animation: study-look 5s ease-in-out forwards; }
    :host(.pose-study) .brows { animation: study-brows 5s ease-in-out forwards; }
    :host(.pose-study) .all { animation: study-body 5s ease-in-out forwards; }

    @keyframes flap-l { 0%, 100% { transform: rotate(-12deg); } 50% { transform: rotate(48deg); } }
    @keyframes flap-r { 0%, 100% { transform: rotate(12deg); } 50% { transform: rotate(-48deg); } }
    @keyframes bob { 50% { transform: translateY(-6px); } }
    @keyframes blink { 0%, 46%, 50%, 100% { transform: scaleY(1); } 48% { transform: scaleY(0.1); } }
    @keyframes study-wing {
      0% { transform: rotate(0); }
      8% { transform: rotate(-150deg); }
      14% { transform: rotate(-136deg); } 20% { transform: rotate(-152deg); } 26% { transform: rotate(-136deg); } 32% { transform: rotate(-152deg); }
      38% { transform: rotate(-140deg); }
      44% { transform: rotate(-62deg); }
      50% { transform: rotate(-52deg); } 56% { transform: rotate(-70deg); } 62% { transform: rotate(-52deg); } 68% { transform: rotate(-70deg); }
      74% { transform: rotate(-52deg); } 80% { transform: rotate(-68deg); } 86% { transform: rotate(-56deg); }
      94%, 100% { transform: rotate(0); }
    }
    @keyframes study-look {
      0% { transform: translate(0, 0); }
      6%, 38% { transform: translate(-3px, -5px); }
      44%, 86% { transform: translate(5px, 1px); }
      94%, 100% { transform: translate(0, 0); }
    }
    @keyframes study-brows { 0%, 30%, 40%, 100% { transform: translateY(0); } 34% { transform: translateY(-7px); } }
    @keyframes study-body {
      0% { transform: rotate(0); }
      10% { transform: rotate(-3deg); } 20% { transform: rotate(2deg); } 30% { transform: rotate(-3deg); }
      40% { transform: rotate(0); }
      46%, 86% { transform: rotate(6deg); }
      92% { transform: rotate(0) translateY(0); }
      96% { transform: translateY(-10px); }
      100% { transform: translateY(0); }
    }
    @media (prefers-reduced-motion: reduce) {
      .all, .wing, .eyes, .pupils, .brows { animation: none !important; }
    }
  `,
})
export class ArchieToon {
  readonly pose = input<ToonPose>('idle');
}
