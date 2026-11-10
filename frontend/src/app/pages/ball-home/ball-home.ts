import { httpResource } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, afterNextRender, computed, effect, inject, signal, viewChild, viewChildren } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { DailyLeg, DailyOut } from '../../core/daily';
import { odds } from '../../core/format';
import { ArchieToon } from '../../shared/archie-toon';
import { Home } from '../home/home';
import { BALL_MENU, freshWins, legKey, uniqueLegs } from './ball';
import { Flight, canFly } from './flight';
import type { BallScene, LabelPlace } from './ball-scene';

const REFRESH_MS = 60_000;
const PARTY_MS = 6_000;

/** La home (D181, D190): il pallone è il menù, la festa parte quando Archie prende un pronostico; sotto, le partite di oggi. */
@Component({
  selector: 'ab-ball-home',
  imports: [ArchieToon, Home, RouterLink],
  templateUrl: './ball-home.html',
  styleUrl: './ball-home.scss',
})
export class BallHome {
  private readonly router = inject(Router);
  private readonly stage = viewChild.required<ElementRef<HTMLElement>>('stage');
  private readonly canvas = viewChild.required<ElementRef<HTMLCanvasElement>>('canvas');
  private readonly labels = viewChildren<ElementRef<HTMLElement>>('label');
  private readonly owl = viewChild<ElementRef<HTMLElement>>('owl');
  private readonly trailBack = viewChild<ElementRef<SVGSVGElement>>('trailBack');
  private readonly trailFront = viewChild<ElementRef<SVGSVGElement>>('trailFront');
  private readonly feathersBack = viewChild<ElementRef<HTMLElement>>('feathersBack');
  private readonly feathersFront = viewChild<ElementRef<HTMLElement>>('feathersFront');
  private flight: Flight | null = null;
  private scene: BallScene | null = null;
  /** Pronostici già festeggiati; null finché non arriva la prima bacheca (quelli già presi non suonano). */
  private celebrated: Set<string> | null = null;
  private partyTimer: ReturnType<typeof setTimeout> | null = null;

  protected readonly menu = BALL_MENU;
  protected readonly fmt = { odds };
  protected readonly confetti = Array.from({ length: 28 }, (_, i) => i);
  protected readonly failed = signal(false);
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
      this.flight?.destroy();
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
        this.startFlight();
      } catch {
        this.failed.set(true); // telefono senza grafica 3D: resta l'elenco delle voci
      }
    });
  }

  /** Archie vola attorno al pallone con scia e piume (D188), solo se il browser sa animare. */
  private startFlight(): void {
    const owl = this.owl(), tb = this.trailBack(), tf = this.trailFront(), fb = this.feathersBack(), ff = this.feathersFront(); // prettier-ignore
    if (!canFly() || !owl || !tb || !tf || !fb || !ff) return;
    this.flight = new Flight({
      stage: this.stage().nativeElement,
      owl: owl.nativeElement,
      trail: { back: tb.nativeElement, front: tf.nativeElement },
      feathers: { back: fb.nativeElement, front: ff.nativeElement },
    });
  }

  /** Tocco su una toppa (o Invio sull'etichetta): la toppa viene davanti e si apre la pagina. */
  protected pick(patch: number): void {
    const entry = this.menu[patch];
    const go = () => void this.router.navigate([entry.link], { queryParams: entry.query });
    if (this.scene) this.scene.bringToFront(patch, go);
    else go();
  }

  private celebrate(leg: DailyLeg): void {
    this.party.set(leg);
    this.scene?.celebrate();
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
