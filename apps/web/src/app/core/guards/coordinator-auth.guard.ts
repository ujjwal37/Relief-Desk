import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '@rd/shared';

export const coordinatorAuthGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isCoordinator()) {
    return true;
  }

  // Redirect unauthenticated / non-coordinator users to login page
  return router.createUrlTree(['/coordinator/login'], {
    queryParams: { returnUrl: state.url },
  });
};
