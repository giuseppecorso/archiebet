import { Component, input } from '@angular/core';

/** Cosa sta facendo Archie: fermo, in volo (home) o allo studio davanti alla lavagna (5 secondi) */
export type ToonPose = 'idle' | 'fly' | 'study';

/** Archie il professore (D188): gufo stilizzato a tinte piatte, occhiali tondi, tocco con nappina, sopracciglia bianche e papillon. Le pose sono solo CSS. */
@Component({
  selector: 'ab-archie-toon',
  host: { '[class]': "'pose-' + pose()", 'aria-hidden': 'true' },
  template: `
    <svg viewBox="0 0 200 200" width="100%" height="100%">
      <g class="all">
        <g class="feet" stroke="#ffc94a" stroke-width="5" stroke-linecap="round">
          <path d="M88 166 v9 M95 167 v9 M105 167 v9 M112 166 v9" />
        </g>
        <path class="tuft" d="M60 72 L50 52 L74 62 Z M140 72 L150 52 L126 62 Z" fill="#d9701f" />
        <path d="M100 54 C135 54 152 82 150 114 C150 148 132 172 100 172 C68 172 50 148 50 114 C48 82 65 54 100 54 Z" fill="#ff9a3c" />
        <circle cx="79" cy="99" r="23" fill="#ffd2a3" />
        <circle cx="121" cy="99" r="23" fill="#ffd2a3" />
        <ellipse cx="100" cy="150" rx="27" ry="19" fill="#ffe8c9" />
        <path d="M86 144 l5 4 l5 -4 M104 144 l5 4 l5 -4 M95 154 l5 4 l5 -4 M80 155 l4 3 l4 -3 M112 155 l4 3 l4 -3"
              fill="none" stroke="#e8a868" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
        <g class="wing left"><path d="M66 100 C34 94 16 122 24 152 C40 143 56 132 68 124 Z" fill="#d9701f" /></g>
        <g class="wing right">
          <path d="M134 100 C166 94 184 122 176 152 C160 143 144 132 132 124 Z" fill="#d9701f" />
          <path class="pen" d="M174 150 L188 166" stroke="#f3f5f9" stroke-width="5" stroke-linecap="round" />
        </g>
        <g class="eyes">
          <g class="pupils">
            <circle cx="81" cy="101" r="6.5" fill="#1d120b" />
            <circle cx="119" cy="101" r="6.5" fill="#1d120b" />
            <circle cx="79" cy="99" r="2" fill="#fff" />
            <circle cx="117" cy="99" r="2" fill="#fff" />
          </g>
        </g>
        <path d="M65.9 94 A15 15 0 0 1 94.1 94 Z M105.9 94 A15 15 0 0 1 134.1 94 Z" fill="#ffc28a" />
        <g fill="rgba(255,255,255,0.18)" stroke="#2a1a10" stroke-width="3.5">
          <circle cx="80" cy="99" r="15" />
          <circle cx="120" cy="99" r="15" />
        </g>
        <path d="M95 98 Q100 93 105 98 M65 97 L55 92 M135 97 L145 92" fill="none" stroke="#2a1a10" stroke-width="3.5" stroke-linecap="round" />
        <path class="brows" d="M64 80 Q77 70 93 79 M107 79 Q123 70 136 80" fill="none" stroke="#f6ead6" stroke-width="6.5" stroke-linecap="round" />
        <path d="M100 109 L93 117 L100 127 L107 117 Z" fill="#ffc94a" />
        <path d="M100 133 L85 125 L85 141 Z M100 133 L115 125 L115 141 Z" fill="#e2484d" />
        <circle cx="100" cy="133" r="4.5" fill="#b8333a" />
        <path d="M74 58 Q100 48 126 58 L124 67 Q100 58 76 67 Z" fill="#1b2233" />
        <path d="M100 30 L148 45 L100 60 L52 45 Z" fill="#2b3550" stroke="#4a5876" stroke-width="2" stroke-linejoin="round" />
        <g class="tassel">
          <path d="M100 45 L134 52 L135 70" fill="none" stroke="#ffc94a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
          <path d="M131 68 h8 l1.5 10 h-11 Z" fill="#ffc94a" />
        </g>
        <circle cx="100" cy="45" r="3.5" fill="#ffc94a" />
      </g>
    </svg>
  `,
  styles: `
    :host { display: block; }
    svg { display: block; overflow: visible; }
    .all, .wing, .eyes, .pupils, .brows, .tassel { transform-box: fill-box; }
    .tassel { transform-origin: 0% 0%; animation: tassel 2.4s ease-in-out infinite; }
    .all { transform-origin: 50% 100%; }
    .wing.left { transform-origin: 100% 10%; }
    .wing.right { transform-origin: 0% 10%; }
    .eyes { transform-origin: 50% 50%; animation: blink 4s infinite; }
    .pen { display: none; }

    /* In volo: ali che sbattono e un leggero su e giù */
    :host(.pose-fly) .wing.left { animation: flap-l 0.42s ease-in-out infinite; }
    :host(.pose-fly) .wing.right { animation: flap-r 0.42s ease-in-out infinite; }
    :host(.pose-fly) .all { animation: bob 0.84s ease-in-out infinite; }
    :host(.pose-fly) .tassel { animation-duration: 0.84s; }

    /* Allo studio (5 s): si gratta la testa, gli viene l'idea, si gira e scrive sulla lavagna */
    :host(.pose-study) .pen { display: inline; }
    :host(.pose-study) .wing.right { animation: study-wing 5s ease-in-out forwards; }
    :host(.pose-study) .pupils { animation: study-look 5s ease-in-out forwards; }
    :host(.pose-study) .brows { animation: study-brows 5s ease-in-out forwards; }
    :host(.pose-study) .all { animation: study-body 5s ease-in-out forwards; }

    @keyframes flap-l { 0%, 100% { transform: rotate(-12deg); } 50% { transform: rotate(48deg); } }
    @keyframes flap-r { 0%, 100% { transform: rotate(12deg); } 50% { transform: rotate(-48deg); } }
    @keyframes tassel { 0%, 100% { transform: rotate(-4deg); } 50% { transform: rotate(6deg); } }
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
      6%, 38% { transform: translate(-2px, -4px); }
      44%, 86% { transform: translate(4px, 1px); }
      94%, 100% { transform: translate(0, 0); }
    }
    @keyframes study-brows { 0%, 30%, 40%, 100% { transform: translateY(0); } 34% { transform: translateY(-5px); } }
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
      .all, .wing, .eyes, .pupils, .brows, .tassel { animation: none !important; }
    }
  `,
})
export class ArchieToon {
  readonly pose = input<ToonPose>('idle');
}
