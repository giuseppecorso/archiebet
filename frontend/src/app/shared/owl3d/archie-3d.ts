import { Component, DestroyRef, ElementRef, afterNextRender, inject, input, signal, viewChild } from '@angular/core';
import type { OwlPose, OwlView } from './owl-view';

/** Archie in 3D (D193). three.js si scarica solo qui; senza grafica 3D (o nei test) resta l'immagine ferma. */
@Component({
  selector: 'ab-archie-3d',
  host: { 'aria-hidden': 'true' },
  template: `
    @if (fallback()) {
      <img src="archie-owl.png" alt="" />
    } @else {
      <canvas #canvas></canvas>
    }
  `,
  styles: `
    :host { display: block; }
    canvas, img { display: block; width: 100%; height: 100%; object-fit: contain; }
  `,
})
export class Archie3d {
  readonly pose = input<OwlPose>('idle');
  private readonly canvas = viewChild<ElementRef<HTMLCanvasElement>>('canvas');
  protected readonly fallback = signal(false);
  private view: OwlView | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.view?.destroy());
    afterNextRender(async () => {
      const canvas = this.canvas()?.nativeElement;
      try {
        if (!canvas || typeof ResizeObserver !== 'function') throw new Error('niente grafica');
        const { OwlView } = await import('./owl-view');
        const calm = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
        this.view = new OwlView(canvas, this.pose(), !calm);
      } catch {
        this.fallback.set(true);
      }
    });
  }
}
