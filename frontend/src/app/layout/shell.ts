import { Component, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { filter, map } from 'rxjs';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth.service';
import { MENU, MenuItem } from '../core/sections';
import { SlipPanel } from '../shared/slip-panel';

/** Cornice comune: intestazione con logo e menu, contenuto della sezione, piè di pagina. */
@Component({
  selector: 'ab-shell',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, SlipPanel],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  private readonly router = inject(Router);
  protected readonly auth = inject(AuthService);
  protected readonly menu = MENU;
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.router.url),
    ),
    { initialValue: this.router.url },
  );

  /** Una voce è accesa anche sulle sue pagine interne (es. Pronostici su /laboratorio) */
  protected isActive(item: MenuItem): boolean {
    const path = this.url().split('?')[0];
    return item.prefixes.some((p) => path === p || path.startsWith(p + '/'));
  }

  protected async logout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigate(['/login']);
  }
}
