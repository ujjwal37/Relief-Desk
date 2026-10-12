import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiClientService, LanguageService, RdTranslatePipe, StoredResource } from '@rd/shared';

const AREAS: Record<string, string> = {
  ward_1: 'Kainakary',
  ward_2: 'Champakulam',
  ward_3: 'Nedumudi',
  ward_4: 'Aluva',
  ward_5: 'Varapuzha',
  ward_6: 'Kothamangalam',
  ward_7: 'Chalakudy',
  ward_8: 'Mala',
  ward_9: 'Anthikad',
  ward_10: 'Meppadi',
  ward_11: 'Vythiri',
  ward_12: 'Kalpetta',
};

@Component({
  selector: 'app-coordinator-teams',
  standalone: true,
  imports: [CommonModule, RouterLink, RdTranslatePipe],
  templateUrl: './coordinator-teams.component.html',
  styleUrl: './coordinator-teams.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorTeamsComponent implements OnInit, OnDestroy {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);

  readonly resources = signal<StoredResource[]>([]);
  readonly typeFilter = signal<string>('all');
  readonly statusFilter = signal<string>('all');
  readonly now = signal(Date.now());
  readonly notice = signal('');

  readonly filtered = computed(() => {
    const type = this.typeFilter();
    const status = this.statusFilter();
    return this.resources().filter((team) => {
      if (type !== 'all' && team.kind !== type) return false;
      if (status !== 'all' && this.statusKey(team) !== status) return false;
      return true;
    });
  });

  private timer: ReturnType<typeof setInterval> | null = null;

  ngOnInit(): void {
    this.reload();
    this.timer = setInterval(() => this.reload(), 5000);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  reload(): void {
    this.api.getResources().subscribe({
      next: (rows) => this.resources.set(rows),
      error: () => this.resources.set([]),
    });
  }

  statusKey(team: StoredResource): string {
    if (team.status === 'busy') return 'dispatched';
    return team.status;
  }

  statusLabel(team: StoredResource): string {
    const key = team.status === 'dispatched' || team.status === 'busy' ? 'busy'
      : team.status === 'en_route' ? 'onTheWay'
      : team.status === 'on_scene' ? 'arrived'
      : team.status === 'available' ? 'free'
      : team.status === 'off_duty' ? 'offDuty'
      : team.status === 'accepted' ? 'accepted'
      : 'free';
    return this.lang.translate(`track.status.${key}`);
  }

  kindLabel(kind: string): string {
    return this.lang.translate(`coord.kind.${kind}`);
  }

  area(team: StoredResource): string {
    return team.area_name || AREAS[team.ward_id] || team.ward_id;
  }

  minutesAgo(team: StoredResource): number {
    this.now();
    const stamp = team.location_updated_at || '';
    if (!stamp) return 0;
    return Math.max(0, Math.round((Date.now() - new Date(stamp).getTime()) / 60000));
  }

  ageLabel(team: StoredResource): string {
    const m = this.minutesAgo(team);
    const key = m < 60 ? 'coord.updatedMin' : 'coord.updatedHour';
    const n = m < 60 ? m : Math.round(m / 60);
    return this.lang.translate(key).replace('{n}', String(n));
  }

  stale(team: StoredResource): boolean {
    return this.minutesAgo(team) >= 20;
  }

  positionStale(team: StoredResource): boolean {
    if (!team.location_source || team.location_source === 'seed') return false;
    return this.minutesAgo(team) >= 2;
  }

  checkIn(team: StoredResource): boolean {
    const busy = ['dispatched', 'busy', 'accepted', 'en_route', 'on_scene', 'returning'].includes(team.status);
    if (!busy) return false;
    const stamps = [team.location_updated_at, team.status_changed_at].filter(Boolean) as string[];
    if (!stamps.length) return true;
    const newest = Math.max(...stamps.map((stamp) => new Date(stamp).getTime()));
    return Date.now() - newest >= 10 * 60 * 1000;
  }

  busyMinutes(team: StoredResource): number | null {
    const busy = ['dispatched', 'busy', 'accepted', 'en_route', 'on_scene', 'returning'].includes(team.status);
    if (!busy || !team.busy_since) return null;
    return Math.max(0, Math.round((Date.now() - new Date(team.busy_since).getTime()) / 60000));
  }

  busyLabel(team: StoredResource): string {
    const minutes = this.busyMinutes(team);
    if (minutes == null) return '';
    return this.lang.translate('track.busyFor').replace('{n}', String(minutes));
  }

  lastSeen(team: StoredResource): string {
    const stamp = team.location_updated_at;
    if (!stamp) return this.lang.translate('track.unseen');
    const parsed = new Date(stamp);
    if (Number.isNaN(parsed.getTime())) return this.lang.translate('track.unseen');
    return this.lang.translate('track.lastSeen').replace('{time}', parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  }

  canDo(team: StoredResource): string {
    return this.lang.translate(`coord.canDo.${team.kind}`).replace('{n}', String(team.capacity_total));
  }

  saveLocation(team: StoredResource, event: Event): void {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    const lat = Number(data.get('lat'));
    const lng = Number(data.get('lng'));
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;
    this.api.updateResourceLocation(team.id, lat, lng).subscribe({
      next: (saved) => {
        this.resources.set(this.resources().map((row) => (row.id === saved.id ? saved : row)));
        this.notice.set(this.lang.translate('coord.savedLocation'));
      },
    });
  }

  fill(kind: string): string {
    return ({ boat: '#0b6e99', medical: '#b42318', food: '#b54708', shelter: '#067647' } as Record<string, string>)[kind] || '#0b6e99';
  }
}
