import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ApiClientService, CallPillComponent, RdTranslatePipe, StoredResource } from '@rd/shared';

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
  private timer: ReturnType<typeof setInterval> | null = null;
  private id = '';

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') || '';
    this.reload();
  }

  ngOnDestroy(): void {
    this.stopShare();
  }

  reload(): void {
    this.api.getTeam(this.id).subscribe({
      next: (team) => this.team.set(team),
      error: () => this.error.set('team.missing'),
    });
  }

  act(action: 'at_scene' | 'done' | 'available'): void {
    this.api.confirmTeam(this.id, action).subscribe({
      next: (team) => {
        this.team.set(team);
        this.notice.set('team.saved');
        if (action !== 'at_scene') this.stopShare();
      },
      error: () => this.error.set('team.missing'),
    });
  }

  toggleShare(on: boolean): void {
    this.sharing.set(on);
    if (!on) {
      this.stopShare();
      return;
    }
    this.sendLocation();
    this.timer = setInterval(() => this.sendLocation(), 45000);
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

  private sendLocation(): void {
    if (!navigator.geolocation) {
      this.error.set('team.noGps');
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        this.api.shareTeamLocation(this.id, pos.coords.latitude, pos.coords.longitude).subscribe({
          next: (team) => this.team.set(team),
          error: () => this.error.set('team.noGps'),
        });
      },
      () => this.error.set('team.noGps'),
      { enableHighAccuracy: true, maximumAge: 15000, timeout: 10000 },
    );
  }

  private stopShare(): void {
    this.sharing.set(false);
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
  }
}
