import { Component, DestroyRef, ElementRef, afterNextRender, effect, inject, input, signal, viewChild } from '@angular/core';
import type { EChartsCoreOption, EChartsType } from 'echarts/core';

/**
 * Un grafico ECharts (D170). La libreria si carica solo quando il grafico compare sullo schermo; il grafico segue la
 * larghezza del riquadro (anche ruotando il telefono). Senza ResizeObserver (test) non disegna niente.
 */
@Component({
  selector: 'ab-chart',
  template: `<div #host class="chart" role="img" [attr.aria-label]="label()" [style.height.px]="height()"></div>`,
  styles: `
    :host { display: block; }
    .chart { width: 100%; }
  `,
})
export class Chart {
  readonly option = input.required<EChartsCoreOption>();
  readonly label = input.required<string>();
  readonly height = input(240);

  private readonly host = viewChild.required<ElementRef<HTMLDivElement>>('host');
  private readonly chart = signal<EChartsType | undefined>(undefined);

  constructor() {
    let resize: ResizeObserver | undefined;
    afterNextRender(async () => {
      if (typeof ResizeObserver === 'undefined') return;
      const { echarts } = await import('./echarts-setup');
      const el = this.host().nativeElement;
      this.chart.set(echarts.init(el, null, { renderer: 'svg' }));
      resize = new ResizeObserver(() => this.chart()?.resize());
      resize.observe(el);
    });
    effect(() => this.chart()?.setOption(this.option(), true));
    inject(DestroyRef).onDestroy(() => {
      resize?.disconnect();
      this.chart()?.dispose();
    });
  }
}
