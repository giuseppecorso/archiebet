import { Component, inject } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth.service';
import { SECTIONS } from '../core/sections';
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
  protected readonly menu = SECTIONS.filter((s) => s.inMenu);

  protected async logout(): Promise<void> {
    await this.auth.logout();
    await this.router.navigate(['/login']);
  }
}
