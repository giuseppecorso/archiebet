import { Component, ElementRef, input, viewChild } from '@angular/core';

/**
 * Il "Perché" di un pronostico in un popup: finestra al centro su PC, pannello dal basso sul telefono.
 * Usa <dialog> del browser: si chiude con la X, con Esc o toccando fuori.
 */
@Component({
  selector: 'ab-why',
  template: `
    <button type="button" class="why-btn" (click)="open()">Perché?</button>
    <dialog #dlg class="why-dlg" (click)="closeOutside($event)" [attr.aria-label]="'Perché: ' + title()">
      <div class="why-box">
        <div class="why-head">
          <h3 class="title">{{ title() }}</h3>
          <button type="button" class="why-x" aria-label="Chiudi" (click)="dlg.close()">✕</button>
        </div>
        @for (r of reasons(); track $index) {
          <p [class.caution]="r.startsWith('⚠')">{{ r }}</p>
        }
      </div>
    </dialog>
  `,
  styles: `
    .why-btn { padding: 2px 10px; min-height: 26px; font: inherit; font-size: 12px; font-weight: 600; color: var(--amber); background: transparent; border: 1px solid var(--line-strong); border-radius: 12px; cursor: pointer; }
    .why-dlg { padding: 0; max-width: min(560px, calc(100vw - 32px)); width: 100%; color: var(--text); background: var(--bg-deep, #0c1410); border: 1px solid var(--line-strong); border-radius: 8px; }
    .why-dlg::backdrop { background: rgb(0 0 0 / 0.6); }
    .why-box { padding: 16px 18px 18px; max-height: 70vh; overflow-y: auto; }
    .why-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 6px; }
    .why-head h3 { margin: 0; font-size: 16px; color: var(--amber); }
    .why-x { min-width: 32px; min-height: 32px; font-size: 16px; color: var(--muted); background: transparent; border: 0; cursor: pointer; }
    p { margin: 8px 0 0; font-size: 14px; line-height: 1.5; }
    p.caution { color: var(--amber); }
    @media (max-width: 600px) {
      .why-dlg { margin: auto 0 0; max-width: 100vw; border-radius: 12px 12px 0 0; }
    }
  `,
})
export class WhyPopup {
  readonly title = input.required<string>();
  readonly reasons = input.required<string[]>();
  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');

  protected open(): void {
    this.dlg().nativeElement.showModal();
  }

  /** Clic sullo sfondo (fuori dal riquadro): chiude */
  protected closeOutside(event: MouseEvent): void {
    if (event.target === this.dlg().nativeElement) this.dlg().nativeElement.close();
  }
}
