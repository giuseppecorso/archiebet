import { httpResource } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, afterNextRender, computed, effect, inject, signal, viewChild, viewChildren } from '@angular/core';
import { Router } from '@angular/router';
import { DailyLeg, DailyOut } from '../../core/daily';
import { odds } from '../../core/format';
import { ArchieToon } from '../../shared/archie-toon';
import { Home } from '../home/home';
import { BALL_MENU, freshWins, legKey, uniqueLegs } from './ball';
import type { BallScene, LabelPlace } from './ball-scene';
import { playHorns } from './horn';

const REFRESH_MS = 60_000;
const PARTY_MS = 6_000;

/** La home (D181): il pallone è il menù, la festa suona quando Archie prende un pronostico; sotto, i riquadri di oggi. */
@Component({
  selector: 'ab-ball-home',
  imports: [ArchieToon, Home],
  templateUrl: './ball-home.html',
  styleUrl: './ball-home.scss',
})
export class BallHome {
  private readonly router = inject(Router);
  private readonly stage = viewChild.required<ElementRef<HTMLElement>>('stage');
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly labels = viewChildren<ElementRef<HTMLElement>>('label');
  private scene: BallScene | null = null;
  private audio: AudioContext | null = null;
  /** Pronostici già festeggiati; null finché non arriva la prima bacheca (quelli già presi non suonano). */
  private celebrated: Set<string> | null = null;
  private partyTimer: ReturnType<typeof setTimeout> | null = null;

  protected readonly menu = BALL_MENU;
  protected readonly fmt = { odds };
  protected readonly confetti = Array.from({ length: 28 }, (_, i) => i);
  protected readonly failed = signal(false);
  protected readonly horns = signal(false);
  protected readonly party = signal<DailyLeg | null>(null);
  protected readonly data = httpResource<DailyOut>(() => '/api/daily');

  protected readonly legs = computed(() => uniqueLegs(this.data.value()?.board ?? []));
  protected readonly won = computed(() => this.legs().filter((leg) => leg.status === 'won'));
  protected readonly open = computed(() => this.legs().filter((leg) => leg.status === 'open'));
  protected readonly closed = computed(() => this.legs().filter((leg) => leg.status === 'won' || leg.status === 'lost').length);

  constructor() {
    const destroy = inject(DestroyRef);
    const timer = setInterval(() => this.data.reload(), REFRESH_MS);
    destroy.onDestroy(() => {
      clearInterval(timer);
      if (this.partyTimer) clearTimeout(this.partyTimer);
      this.scene?.destroy();
      void this.audio?.close();
    });

    effect(() => {
      if (!this.data.hasValue()) return;
      const legs = this.legs();
      if (this.celebrated === null) {
        this.celebrated = new Set(legs.filter((leg) => leg.status === 'won').map(legKey));
        return;
      }
      const fresh = freshWins(this.celebrated, legs);
      fresh.forEach((leg) => this.celebrated?.add(legKey(leg)));
      if (fresh.length) this.celebrate(fresh[fresh.length - 1]);
    });

    afterNextRender(async () => {
      try {
        // three.js si scarica solo qui, quando serve
        const { BallScene } = await import('./ball-scene');
        this.scene = new BallScene(this.stage().nativeElement, this.canvas().nativeElement, (places) => this.place(places), (patch) => this.pick(patch)); // prettier-ignore
      } catch {
        this.failed.set(true); // telefono senza grafica 3D: resta l'elenco delle voci
      }
    });
  }

  /** Tocco su una toppa (o Invio sull'etichetta): la toppa viene davanti e si apre la pagina. */
  protected pick(patch: number): void {
    const entry = this.menu[patch];
    const go = () => void this.router.navigate([entry.link], { queryParams: entry.query });
    if (this.scene) this.scene.bringToFront(patch, go);
    else go();
  }

  /** L'interruttore delle trombe: il browser lascia partire l'audio solo dopo un tocco, e questo lo è. */
  protected toggleHorns(): void {
    const on = !this.horns();
    this.horns.set(on);
    if (on) {
      this.audio ??= new AudioContext();
      void this.audio.resume();
      playHorns(this.audio);
    }
  }

  /** Fa vedere la festa senza aspettare una partita. */
  protected demo(): void {
    this.celebrate({
      match_id: 0, kickoff_at: '', competition: 'Prova', home: 'Como', away: 'Cagliari',
      market: 'OU2.5', selection: 'over', event: 'Più di 2,5 gol', p: 0.55, price: 1.85, status: 'won', score: '2-1',
    }); // prettier-ignore
  }

  private celebrate(leg: DailyLeg): void {
    this.party.set(leg);
    this.scene?.celebrate();
    if (this.horns() && this.audio) playHorns(this.audio);
    if (this.partyTimer) clearTimeout(this.partyTimer);
    this.partyTimer = setTimeout(() => this.party.set(null), PARTY_MS);
  }

  /** Le etichette seguono le toppe: si spostano a mano, senza passare da Angular, a ogni fotogramma. */
  private place(places: LabelPlace[]): void {
    this.labels().forEach((ref, i) => {
      const { x, y, facing } = places[i];
      const el = ref.nativeElement;
      el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -50%) scale(${(0.7 + 0.3 * facing).toFixed(3)})`;
      el.style.opacity = facing.toFixed(2);
      el.style.visibility = facing > 0.02 ? 'visible' : 'hidden';
    });
  }
}
