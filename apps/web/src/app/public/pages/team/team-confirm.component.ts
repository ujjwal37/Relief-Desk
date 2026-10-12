import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiClientService, CallPillComponent, RdTranslatePipe, StoredResource, TeamFix } from '@rd/shared';

type NextAction = 'accept' | 'on_the_way' | 'arrived' | 'complete' | 'off_duty' | 'free';

@Component({
  selector: 'app-team-confirm',
  standalone: true,
  imports: [CommonModule, RouterLink, RdTranslatePipe, CallPillComponent],
  templateUrl: './team-confirm.component.html',
  styleUrl: './team-confirm.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class TeamConfirmComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private api = inject(ApiClientService);

  readonly team = signal<StoredResource | null>(null);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  readonly sharing = signal(false);
  readonly permDenied = signal(false);
  readonly lowAccuracy = signal(false);
  readonly offline = signal(false);
  readonly queued = signal(false);
  readonly lastSent = signal<string | null>(null);
  readonly outcomeOpen = signal(false);
  readonly accuracyM = signal<number | null>(null);

  private timer: ReturnType<typeof setInterval> | null = null;
  private watchId: number | null = null;
  private latest: TeamFix | null = null;
  private id = '';
  private token = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    this.token = this.route.snapshot.queryParamMap?.get('token') || '';
    const saved = this.readQueue();
    if (saved) {
      this.latest = saved;
      this.queued.set(true);
    }
    this.reload();
    window.addEventListener('online', this.onOnline);
    window.addEventListener('offline', this.onOffline);
  }

  ngOnDestroy(): void {
    this.stopShare();
    window.removeEventListener('online', this.onOnline);
    window.removeEventListener('offline', this.onOffline);
  }

  reload(): void {
    this.api.getTeam(this.id).subscribe({
      next: (team) => this.team.set(team),
      error: () => this.error.set('team.missing'),
    });
  }

  nextAction(team: StoredResource): NextAction | null {
    switch (team.status) {
      case 'dispatched':
      case 'busy':
        return 'accept';
      case 'accepted':
        return 'on_the_way';
      case 'en_route':
        return 'arrived';
      case 'on_scene':
        return 'complete';
      case 'available':
        return 'off_duty';
      case 'off_duty':
        return 'free';
      default:
        return null;
    }
  }

  actionKey(action: NextAction): string {
    return {
      accept: 'track.accepted',
      on_the_way: 'track.onTheWay',
      arrived: 'track.arrived',
      complete: 'track.markCompleted',
      off_duty: 'track.offDuty',
      free: 'track.free',
    }[action];
  }

  statusKey(team: StoredResource): string {
    if (team.status === 'dispatched' || team.status === 'busy') return 'busy';
    if (team.status === 'en_route') return 'onTheWay';
    if (team.status === 'on_scene') return 'arrived';
    if (team.status === 'available') return 'free';
    if (team.status === 'off_duty') return 'offDuty';
    if (team.status === 'accepted') return 'accepted';
    return 'free';
  }

  sourceKey(team: StoredResource): string {
    if (team.simulated || team.location_source === 'simulated') return 'track.simulated';
    if (team.location_source === 'gps') return 'track.liveGps';
    return 'track.base';
  }

  startAction(action: NextAction): void {
    if (action === 'complete') {
      this.outcomeOpen.set(true);
      return;
    }
    this.sendStatus(action);
  }

  submitComplete(event: Event): void {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    const people = Number(data.get('people'));
    const follow = String(data.get('follow') || '');
    if (!Number.isFinite(people) || follow !== 'yes' && follow !== 'no') {
      this.error.set('track.outcomeNeed');
      return;
    }
    this.sendStatus('complete', { people_helped: people, needs_follow_up: follow === 'yes' });
    this.outcomeOpen.set(false);
  }

  toggleShare(on: boolean): void {
    if (!on) {
      this.stopShare();
      return;
    }
    if (!this.token) {
      this.error.set('track.missingToken');
      return;
    }
    const geo = navigator.geolocation;
    if (!geo) {
      this.error.set('track.noGps');
      return;
    }
    this.permDenied.set(false);
    this.error.set(null);
    this.sharing.set(true);
    this.watchId = geo.watchPosition(
      (pos) => this.onFix(pos),
      (err) => this.onGeoError(err),
      { enableHighAccuracy: true, maximumAge: 5000, timeout: 12000 },
    );
    this.sendLatest();
    this.timer = setInterval(() => this.sendLatest(), 8000);
  }

  clock(value: string): string {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  trailPoints(team: StoredResource): string {
    const trail = team.location_trail || [];
    if (trail.length < 2) return '';
    const minLa = Math.min(...trail.map((p) => p.lat));
    const maxLa = Math.max(...trail.map((p) => p.lat));
    const minLo = Math.min(...trail.map((p) => p.lng));
    const maxLo = Math.max(...trail.map((p) => p.lng));
    const fx = (lng: number) => 16 + ((lng - minLo) / Math.max(1e-6, maxLo - minLo)) * 300;
    const fy = (lat: number) => 16 + (1 - (lat - minLa) / Math.max(1e-6, maxLa - minLa)) * 140;
    return trail.map((p) => `${fx(p.lng).toFixed(1)},${fy(p.lat).toFixed(1)}`).join(' ');
  }

  private sendStatus(action: string, extra: { people_helped?: number; needs_follow_up?: boolean } = {}): void {
    if (!this.token) {
      this.error.set('track.missingToken');
      return;
    }
    const post = () => this.api.postTeamStatus(this.id, { action, token: this.token, ...extra }).subscribe({
      next: (team) => {
        this.team.set(team);
        this.notice.set('team.saved');
        this.error.set(null);
      },
      error: () => this.error.set('team.missing'),
    });
    if (this.sharing() && this.latest) {
      this.api.postTeamLocation(this.id, { ...this.latest, token: this.token }).subscribe({
        next: (team) => {
          this.team.set(team);
          this.lastSent.set(new Date().toISOString());
          post();
        },
        error: () => post(),
      });
      return;
    }
    post();
  }

  private onFix(pos: GeolocationPosition): void {
    const accuracy = pos.coords.accuracy;
    this.accuracyM.set(Number.isFinite(accuracy) ? Math.round(accuracy) : null);
    this.lowAccuracy.set(Number.isFinite(accuracy) && accuracy > 100);
    this.latest = {
      lat: pos.coords.latitude,
      lng: pos.coords.longitude,
      accuracy: Number.isFinite(accuracy) ? accuracy : null,
      heading: Number.isFinite(pos.coords.heading ?? NaN) ? pos.coords.heading : null,
      speed: Number.isFinite(pos.coords.speed ?? NaN) ? pos.coords.speed : null,
      ts: new Date(pos.timestamp || Date.now()).toISOString(),
    };
    if (navigator.onLine === false) {
      this.queueLatest();
    }
  }

  private onGeoError(err: { code?: number }): void {
    this.sharing.set(false);
    this.stopWatch();
    if (err?.code === 1) {
      this.permDenied.set(true);
      this.error.set('track.permDenied');
      return;
    }
    this.error.set('track.noGps');
  }

  private sendLatest(): void {
    const fix = this.latest || this.readQueue();
    if (!fix || !this.token) return;
    if (navigator.onLine === false) {
      this.queueLatest();
      return;
    }
    this.api.postTeamLocation(this.id, { ...fix, token: this.token }).subscribe({
      next: (team) => {
        this.team.set(team);
        this.lastSent.set(new Date().toISOString());
        this.queued.set(false);
        this.offline.set(false);
        localStorage.removeItem(this.queueKey());
      },
      error: () => this.queueLatest(),
    });
  }

  private queueLatest(): void {
    if (!this.latest) return;
    this.queued.set(true);
    this.offline.set(navigator.onLine === false);
    try {
      localStorage.setItem(this.queueKey(), JSON.stringify(this.latest));
    } catch { /* private mode */ }
  }

  private readQueue(): TeamFix | null {
    try {
      const raw = localStorage.getItem(this.queueKey());
      return raw ? JSON.parse(raw) as TeamFix : null;
    } catch {
      return null;
    }
  }

  private queueKey(): string {
    return `rd_team_fix_${this.id}`;
  }

  private onOnline = (): void => {
    this.offline.set(false);
    if (this.sharing() || this.queued()) this.sendLatest();
  };

  private onOffline = (): void => {
    this.offline.set(true);
    if (this.latest) this.queueLatest();
  };

  private stopShare(): void {
    this.sharing.set(false);
    this.stopWatch();
  }

  private stopWatch(): void {
    if (this.watchId != null && navigator.geolocation) {
      navigator.geolocation.clearWatch(this.watchId);
      this.watchId = null;
    }
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
