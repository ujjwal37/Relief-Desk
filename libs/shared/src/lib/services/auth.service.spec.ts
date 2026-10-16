import { TestBed } from '@angular/core/testing';
import { AuthService, DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_TOKEN } from './auth.service';

describe('AuthService', () => {
  let service: AuthService;

  function sessionBody(token: string) {
    return {
      token,
      email: DEMO_COORDINATOR_EMAIL,
      role: 'coordinator',
      display_name: 'Kerala Emergency Coordinator',
    };
  }

  function mockFetch(body: unknown, ok = true): jasmine.Spy {
    return spyOn(window, 'fetch').and.resolveTo({
      ok,
      json: async () => body,
    } as Response);
  }

  beforeEach(() => {
    TestBed.configureTestingModule({});
    service = TestBed.inject(AuthService);
    service.logout();
  });

  it('should be initialized unauthenticated by default', () => {
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.isCoordinator()).toBeFalse();
    expect(service.currentUser()).toBeNull();
    expect(service.getToken()).toBeNull();
  });

  it('stores the coordinator session returned by the API', async () => {
    mockFetch(sessionBody('signed-test-token'));
    const res = await service.login(DEMO_COORDINATOR_EMAIL, 'from-the-form');
    expect(res.success).toBeTrue();
    expect(service.isAuthenticated()).toBeTrue();
    expect(service.isCoordinator()).toBeTrue();
    expect(service.currentUser()?.email).toBe(DEMO_COORDINATOR_EMAIL);
    expect(service.currentUser()?.role).toBe('coordinator');
    expect(service.getToken()).toBe('signed-test-token');
  });

  it('one-click demo login posts to demo-login with no password', async () => {
    const fetchSpy = mockFetch(sessionBody('signed-demo-jwt'));
    const ok = await service.loginDemo();
    expect(ok).toBeTrue();
    const [url, init] = fetchSpy.calls.mostRecent().args as [string, RequestInit];
    expect(url).toBe('/api/auth/demo-login');
    expect(JSON.parse(String(init.body))).toEqual({});
    expect(service.getToken()).toBe('signed-demo-jwt');
  });

  it('should reject invalid coordinator credentials', async () => {
    mockFetch({}, false);
    const res = await service.login('wrong@reliefdesk.internal', 'badpassword');
    expect(res.success).toBeFalse();
    expect(res.error).toBe('Invalid email or password');
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.isCoordinator()).toBeFalse();
  });

  it('should clear session on logout', async () => {
    mockFetch(sessionBody('signed-test-token'));
    await service.login(DEMO_COORDINATOR_EMAIL, 'from-the-form');
    expect(service.isAuthenticated()).toBeTrue();

    service.logout();
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.currentUser()).toBeNull();
    expect(service.getToken()).toBeNull();
  });

  it('drops a stored fixed demo token', () => {
    localStorage.setItem(
      'rd_auth_session',
      JSON.stringify({
        email: DEMO_COORDINATOR_EMAIL,
        role: 'coordinator',
        token: DEMO_COORDINATOR_TOKEN,
      }),
    );
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    const fresh = TestBed.inject(AuthService);
    expect(fresh.currentUser()).toBeNull();
    expect(fresh.isAuthenticated()).toBeFalse();
  });
});
