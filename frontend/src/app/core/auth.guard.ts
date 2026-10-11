import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from './auth.service';

/** Lascia passare solo chi ha fatto login; gli altri vanno alla pagina di accesso. */
export const authGuard: CanActivateFn = async () => {
  // inject() va chiamato prima di qualunque await
  const auth = inject(AuthService);
  const router = inject(Router);
  if (auth.user() ?? (await auth.loadSession())) {
    return true;
  }
  return router.createUrlTree(['/login']);
};
