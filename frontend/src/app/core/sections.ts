/** Sezioni dell'app (specifiche, sezione 3). Il menu e le rotte nascono da questo elenco. */
export interface Section {
  path: string;
  label: string;
  /** true = nel menu principale; false = raggiungibile da un'icona (es. Impostazioni) */
  inMenu: boolean;
  /** Fase in cui la sezione prende vita */
  phase: number;
  summary: string;
  features: string[];
}

export const SECTIONS: Section[] = [
  {
    path: 'partite',
    label: 'Partite',
    inMenu: true,
    phase: 1,
    summary: 'La dashboard: tutte le partite, la multipla del giorno e la tua schedina.',
    features: [
      'Elenco partite di Serie A, B e C con filtri per campionato',
      'Pagina partita con statistiche vere',
      'Multipla del giorno e "Archie, fammi una multipla"',
      'ArchieTV, notizie e Chiedi ad Archie',
    ],
  },
  {
    path: 'schedine',
    label: 'Le mie schedine',
    inMenu: true,
    phase: 2,
    summary: 'Le tue giocate, reali e simulate, seguite fino alla fine.',
    features: [
      'Registra una giocata con quote precompilate',
      'Schedine aperte e chiuse, reali e simulate',
      'Segui live e termometro della speranza',
      'Archie rivede la schedina: sfortuna o errore?',
    ],
  },
  {
    path: 'statistiche',
    label: 'Le mie statistiche',
    inMenu: true,
    phase: 2,
    summary: 'Come prevedi, non solo quanto vinci.',
    features: [
      'Riepilogo per settimana, 30 giorni, stagione',
      'Tu contro Archie e CLV',
      'Dove vinci e dove perdi',
      'Il tuo stile di gioco e il tuo regolamento personale',
    ],
  },
  {
    path: 'laboratorio',
    label: 'Laboratorio',
    inMenu: true,
    phase: 1.5,
    summary: 'Studia il passato di campionati e squadre.',
    features: ['Numeri e classifica di ogni campionato e stagione', 'Storia di ogni squadra', 'Strategie provate sul passato (Fase 7)'],
  },
  {
    path: 'gioca',
    label: 'Gioca',
    inMenu: true,
    phase: 6,
    summary: 'Solo crediti finti: per allenare il fiuto.',
    features: [
      'Simulatore partita con 10.000 simulazioni',
      'Comandi "E se..."',
      'Sfida contro Archie con classifica',
    ],
  },
  {
    path: 'impostazioni',
    label: 'Impostazioni',
    inMenu: false,
    phase: 2,
    summary: 'Limiti di gioco e preferenze.',
    features: [
      'Budget settimanale e mensile',
      'Campionati seguiti e bookmaker',
      'Soglie di valore e squadra del cuore',
    ],
  },
];
