import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ShowMore } from './show-more';

@Component({
  imports: [ShowMore],
  template: `
    <ul>
      @for (n of items.slice(0, open() ? undefined : 3); track n) {
        <li>{{ n }}</li>
      }
    </ul>
    <ab-show-more [total]="items.length" [limit]="3" [(expanded)]="open" />
  `,
})
class Host {
  items = [1, 2, 3, 4, 5];
  open = signal(false);
}

describe('ShowMore', () => {
  it('mostra le prime righe e poi tutte, e torna indietro', async () => {
    const fixture = TestBed.createComponent(Host);
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    const button = () => el.querySelector('button')!;

    expect(el.querySelectorAll('li').length).toBe(3);
    expect(button().textContent).toContain('Mostra tutte (5)');
    expect(button().getAttribute('aria-expanded')).toBe('false');

    button().click();
    await fixture.whenStable();
    expect(el.querySelectorAll('li').length).toBe(5);
    expect(button().textContent).toContain('Mostra meno');

    button().click();
    await fixture.whenStable();
    expect(el.querySelectorAll('li').length).toBe(3);
  });

  it('non compare se le righe sono poche', async () => {
    const fixture = TestBed.createComponent(Host);
    fixture.componentInstance.items = [1, 2];
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).querySelector('button')).toBeNull();
  });
});
