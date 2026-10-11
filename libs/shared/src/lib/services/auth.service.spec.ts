import { TestBed } from '@angular/core/testing';
import {
  AuthService,
  DEMO_COORDINATOR_EMAIL,
  DEMO_COORDINATOR_PASSWORD,
  DEMO_COORDINATOR_TOKEN,
} from './auth.service';

describe('AuthService', () => {
  let service: AuthService;

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

  it('should authenticate demo coordinator with pre-seeded synthetic credentials', async () => {
    const res = await service.login(DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_PASSWORD);
    expect(res.success).toBeTrue();
    expect(service.isAuthenticated()).toBeTrue();
    expect(service.isCoordinator()).toBeTrue();
    expect(service.currentUser()?.email).toBe(DEMO_COORDINATOR_EMAIL);
    expect(service.currentUser()?.role).toBe('coordinator');
    expect(service.getToken()).toBe(DEMO_COORDINATOR_TOKEN);
  });

  it('should reject invalid coordinator credentials', async () => {
    const res = await service.login('wrong@reliefdesk.internal', 'badpassword');
    expect(res.success).toBeFalse();
    expect(res.error).toBe('Invalid email or password');
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.isCoordinator()).toBeFalse();
  });

  it('should clear session on logout', async () => {
    await service.login(DEMO_COORDINATOR_EMAIL, DEMO_COORDINATOR_PASSWORD);
    expect(service.isAuthenticated()).toBeTrue();

    service.logout();
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.currentUser()).toBeNull();
    expect(service.getToken()).toBeNull();
  });
});
