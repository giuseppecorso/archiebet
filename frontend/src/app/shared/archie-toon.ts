import { Component, input } from '@angular/core';

/** Cosa sta facendo Archie: fermo, in volo (home) o allo studio davanti alla lavagna (5 secondi) */
export type ToonPose = 'idle' | 'fly' | 'study';

/** Archie (D186): gufo reale dal piumaggio fulvo, disegnato al naturale (sfumature, disco facciale, occhi ambra). Le pose sono solo CSS. */
@Component({
  selector: 'ab-archie-toon',
  host: { '[class]': "'pose-' + pose()", 'aria-hidden': 'true' },
  template: `
    <svg viewBox="0 0 200 200" width="100%" height="100%">
      <defs>
        <linearGradient id="ar-body" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#d98a3e" /><stop offset="1" stop-color="#8f4c1c" />
        </linearGradient>
        <linearGradient id="ar-wing" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#b9682a" /><stop offset="1" stop-color="#5f3212" />
        </linearGradient>
        <linearGradient id="ar-chest" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#f3dcb4" /><stop offset="1" stop-color="#dcae74" />
        </linearGradient>
        <radialGradient id="ar-disc" cx="50%" cy="50%" r="50%">
          <stop offset="0.35" stop-color="#f6e3c2" /><stop offset="1" stop-color="#d99a55" />
        </radialGradient>
        <radialGradient id="ar-iris" cx="50%" cy="50%" r="50%">
          <stop offset="0.3" stop-color="#ffcf40" /><stop offset="1" stop-color="#ef8410" />
        </radialGradient>
      </defs>
      <g class="all">
        <g class="feet" stroke="#caa04a" stroke-width="4" stroke-linecap="round">
          <path d="M86 162 v10 M94 163 v10 M106 163 v10 M114 162 v10" />
        </g>
        <path class="tuft" d="M70 76 C61 60 57 48 55 36 C69 44 81 54 90 66 Z M130 76 C139 60 143 48 145 36 C131 44 119 54 110 66 Z" fill="#8f4c1c" />
        <path d="M100 58 C132 58 150 82 148 112 C150 142 136 168 100 168 C64 168 50 142 52 112 C50 82 68 58 100 58 Z" fill="url(#ar-body)" />
        <path d="M62 84 q5 5 10 0 M128 84 q5 5 10 0 M58 100 q4 4 8 0 M134 100 q4 4 8 0" fill="none" stroke="#7a4317" stroke-width="2" stroke-linecap="round" opacity="0.55" />
        <ellipse cx="100" cy="138" rx="27" ry="28" fill="url(#ar-chest)" />
        <path d="M88 121 v7 M100 119 v7 M112 121 v7 M82 135 v7 M94 134 v7 M106 134 v7 M118 135 v7 M88 149 v7 M100 149 v7 M112 149 v7"
              fill="none" stroke="#7a4317" stroke-width="2.6" stroke-linecap="round" opacity="0.8" />
        <g class="wing left">
          <path d="M66 98 C32 92 14 122 22 152 C40 142 56 130 68 122 Z" fill="url(#ar-wing)" />
          <path d="M58 104 C40 110 30 128 27 144 M62 111 C48 118 41 130 37 140 M66 117 C57 122 51 130 48 136" fill="none" stroke="#f0c98f" stroke-width="1.8" stroke-linecap="round" opacity="0.45" />
        </g>
        <g class="wing right">
          <path d="M134 98 C168 92 186 122 178 152 C160 142 144 130 132 122 Z" fill="url(#ar-wing)" />
          <path d="M142 104 C160 110 170 128 173 144 M138 111 C152 118 159 130 163 140 M134 117 C143 122 149 130 152 136" fill="none" stroke="#f0c98f" stroke-width="1.8" stroke-linecap="round" opacity="0.45" />
          <path class="pen" d="M176 150 L190 166" stroke="#f3f5f9" stroke-width="5" stroke-linecap="round" />
        </g>
        <circle cx="80" cy="95" r="23" fill="url(#ar-disc)" stroke="#8f4c1c" stroke-width="2" />
        <circle cx="120" cy="95" r="23" fill="url(#ar-disc)" stroke="#8f4c1c" stroke-width="2" />
        <g class="eyes">
          <circle cx="81" cy="95" r="12.5" fill="url(#ar-iris)" stroke="#24130a" stroke-width="2.5" />
          <circle cx="119" cy="95" r="12.5" fill="url(#ar-iris)" stroke="#24130a" stroke-width="2.5" />
          <g class="pupils">
            <circle cx="82" cy="96" r="6.5" fill="#120b08" />
            <circle cx="118" cy="96" r="6.5" fill="#120b08" />
            <circle cx="79.5" cy="93" r="2" fill="#fff" />
            <circle cx="115.500" cy="93" r="2" fill="#fff" />
          </g>
        </g>
        <path class="brows" d="M100 88 C90 73 74 67 55 69 C65 76 73 80 80 82 C88 80 95 83 100 88 Z M100 88 C110 73 126 67 145 69 C135 76 127 80 120 82 C112 80 105 83 100 88 Z"
              fill="#6b3712" />
        <path d="M100 98 C94 102 93 111 100 121 C107 111 106 102 100 98 Z" fill="#3b2a22" />
        <path d="M99 101 C96 104 96 109 98 113" fill="none" stroke="#8a7468" stroke-width="1.4" stroke-linecap="round" />
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
      .all, .wing, .eyes, .pupils, .brows { animation: none !important; }
    }
  `,
})
export class ArchieToon {
  readonly pose = input<ToonPose>('idle');
}
