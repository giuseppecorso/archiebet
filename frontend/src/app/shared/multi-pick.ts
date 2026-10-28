import { Component, ElementRef, computed, input, model, viewChild } from '@angular/core';

export interface PickOption {
  value: string;
  label: string;
  /** Titolo del gruppo (es. il paese): le opzioni dello stesso gruppo stanno insieme */
  group?: string;
}

/**
 * Scelta multipla in un popup (giorni, campionati): il pulsante dice cosa è scelto, la finestra ha le caselle.
 * Nessuna scelta = "tutti" (se `allLabel` è dato).
 */
@Component({
  selector: 'ab-multi-pick',
  template: `
    <button type="button" class="mp-btn" (click)="dlg.showModal()" [attr.aria-label]="label() + ': ' + summary()">
      <span>{{ summary() }}</span><span aria-hidden="true">▾</span>
    </button>
    <dialog #dlg class="mp-dlg" (click)="closeOutside($event)" [attr.aria-label]="label()">
      <div class="mp-box">
        <div class="mp-head">
          <h3 class="title">{{ label() }}</h3>
          <button type="button" class="mp-x" aria-label="Chiudi" (click)="dlg.close()">✕</button>
        </div>
        <div class="mp-list">
          @for (o of options(); track o.value; let i = $index) {
            @if (o.group && o.group !== options()[i - 1]?.group) {
              <span class="mp-group">{{ o.group }}</span>
            }
            <label class="mp-item">
              <input type="checkbox" [checked]="selected().includes(o.value)" (change)="toggle(o.value)" />
              {{ o.label }}
            </label>
          }
        </div>
        <div class="mp-actions">
          <button type="button" class="mp-all" (click)="selected.set([])">{{ allLabel() ? allLabel() : 'Nessuno' }}</button>
          <button type="button" class="btn-primary" (click)="dlg.close()">Fatto</button>
        </div>
      </div>
    </dialog>
  `,
  styles: `
    :host { display: block; }
    .mp-btn { display: flex; justify-content: space-between; gap: 8px; width: 100%; min-height: 30px; padding: 2px 8px; font: inherit; font-size: 13px; color: var(--text); text-align: left; background: var(--bg-deep); border: 1px solid var(--line-strong); border-radius: 4px; cursor: pointer; }
    .mp-dlg { padding: 0; max-width: min(460px, calc(100vw - 32px)); width: 100%; color: var(--text); background: var(--bg-deep, #0c1410); border: 1px solid var(--line-strong); border-radius: 8px; }
    .mp-dlg::backdrop { background: rgb(0 0 0 / 0.6); }
    .mp-box { display: flex; flex-direction: column; max-height: 75vh; padding: 14px 16px; }
    .mp-head { display: flex; justify-content: space-between; align-items: center; }
    .mp-head h3 { margin: 0; font-size: 16px; color: var(--amber); }
    .mp-x { min-width: 32px; min-height: 32px; font-size: 16px; color: var(--muted); background: transparent; border: 0; cursor: pointer; }
    .mp-list { overflow-y: auto; margin: 8px 0; }
    .mp-group { display: block; margin: 10px 0 2px; font-size: 11px; font-weight: 700; letter-spacing: 1px; color: var(--muted); text-transform: uppercase; }
    .mp-item { display: flex; align-items: center; gap: 10px; min-height: 36px; font-size: 14px; cursor: pointer; }
    .mp-item input { width: 18px; height: 18px; accent-color: var(--amber); }
    .mp-actions { display: flex; justify-content: space-between; gap: 8px; }
    .mp-actions button { min-height: 36px; padding: 4px 14px; }
    .mp-all { font: inherit; font-size: 13px; font-weight: 600; color: var(--amber); background: transparent; border: 1px solid var(--amber); border-radius: 4px; cursor: pointer; }
  `,
})
export class MultiPick {
  readonly label = input.required<string>();
  readonly options = input.required<PickOption[]>();
  /** Testo quando non è scelto niente (es. "Tutti") */
  readonly allLabel = input<string>('');
  readonly selected = model<string[]>([]);
  private readonly dlg = viewChild.required<ElementRef<HTMLDialogElement>>('dlg');

  protected readonly summary = computed(() => {
    const chosen = this.options().filter((o) => this.selected().includes(o.value));
    if (!chosen.length) return this.allLabel() || 'Nessuno';
    return chosen.length <= 2 ? chosen.map((o) => o.label).join(', ') : `${chosen.length} scelti`;
  });

  protected toggle(value: string): void {
    this.selected.update((s) => (s.includes(value) ? s.filter((v) => v !== value) : [...s, value]));
  }

  protected closeOutside(event: MouseEvent): void {
    if (event.target === this.dlg().nativeElement) this.dlg().nativeElement.close();
  }
}
