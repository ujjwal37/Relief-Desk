import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { App } from './app';
import { coordinatorAuthGuard } from './core/guards/coordinator-auth.guard';
import { AuthService, DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_PASSWORD } from '@rd/shared';

describe('App & Routing Shell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter([])],
    }).compileComponents();
  });

  it('should create the app shell with router outlet', () => {
    const fixture = TestBed.createComponent(App);
    const app = fixture.componentInstance;
    expect(app).toBeTruthy();
  });

  it('coordinatorAuthGuard should redirect unauthenticated user to /coordinator/login', () => {
    const authService = TestBed.inject(AuthService);
    const router = TestBed.inject(Router);
    authService.logout();

    const result = TestBed.runInInjectionContext(() =>
      coordinatorAuthGuard({} as any, { url: '/coordinator/command' } as any)
    );

    expect(typeof result).toBe('object');
    const urlTree = result as any;
    expect(urlTree.toString()).toContain('/coordinator/login?returnUrl=%2Fcoordinator%2Fcommand');
  });

  it('coordinatorAuthGuard should allow access when coordinator is signed in', async () => {
    const authService = TestBed.inject(AuthService);
    // Sign-in talks to the API; stub the response a real demo login returns.
    spyOn(window, 'fetch').and.resolveTo(new Response(JSON.stringify({ token: 'jwt', email: DEMO_COORDINATOR_EMAIL, role: 'coordinator' }), { status: 200 }));
    const signedIn = await authService.login(DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_PASSWORD);
    expect(signedIn.success).toBeTrue();

    const result = TestBed.runInInjectionContext(() =>
      coordinatorAuthGuard({} as any, { url: '/coordinator/command' } as any)
    );

    expect(result).toBeTrue();
  });
});
