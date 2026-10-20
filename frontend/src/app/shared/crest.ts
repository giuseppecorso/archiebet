import { Component, computed, input, signal } from '@angular/core';
import { TeamRef } from '../core/football';

/** Tinta stabile ricavata dal nome: ogni squadra senza stemma ha sempre lo stesso colore */
export function hueOf(name: string): number {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return h;
}

/** Iniziali per il distintivo di riserva: "Hellas Verona" → "HV", "Inter" → "IN" */
export function initials(name: string): string {
  const words = name.replace(/[^\p{L}\p{N} ]/gu, ' ').split(' ').filter((w) => w.length > 1 || /\d/.test(w));
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? name).slice(0, 2).toUpperCase();
}

/** Stemma della squadra (da API-Football, salvato sul PC, D84); se manca, distintivo colorato con le iniziali. */
@Component({
  selector: 'ab-crest',
  template: `
    @if (!failed()) {
      <img [src]="src()" [width]="size()" [height]="size()" alt="" loading="lazy" decoding="async" (error)="failed.set(true)" />
    } @else {
      <span class="badge" [style.--hue]="hue()" aria-hidden="true">{{ letters() }}</span>
    }
  `,
  styles: `
    :host { display: inline-flex; flex: none; width: var(--crest, 22px); height: var(--crest, 22px); }
    img { width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 1px 2px rgb(0 0 0 / 0.6)); }
    .badge {
      display: grid; place-items: center; width: 100%; height: 100%; border-radius: 50%;
      font-size: calc(var(--crest, 22px) * 0.4); font-weight: 700; letter-spacing: 0.5px; color: #fff;
      background: radial-gradient(circle at 30% 30%, hsl(var(--hue) 70% 50%), hsl(var(--hue) 60% 28%));
      border: 1px solid hsl(var(--hue) 70% 60% / 0.6);
    }
  `,
  host: { '[style.--crest.px]': 'size()' },
})
export class Crest {
  readonly team = input.required<TeamRef>();
  readonly size = input(22);
  protected readonly failed = signal(false);
  protected readonly src = computed(() => `/api/media/team/${this.team().id}.png`);
  protected readonly hue = computed(() => hueOf(this.team().name));
  protected readonly letters = computed(() => initials(this.team().name));
}

/** Logo del campionato; se manca non mostra nulla. */
@Component({
  selector: 'ab-league-logo',
  template: `
    @if (!failed()) {
      <img [src]="'/api/media/competition/' + code() + '.png'" [width]="size()" [height]="size()" alt="" loading="lazy"
           (error)="failed.set(true)" />
    }
  `,
  styles: `
    :host { display: inline-flex; flex: none; }
    img { object-fit: contain; border-radius: 3px; background: #fff; padding: 2px; }
  `,
})
export class LeagueLogo {
  readonly code = input.required<string>();
  readonly size = input(18);
  protected readonly failed = signal(false);
}
