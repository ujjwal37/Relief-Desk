import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiClientService, LanguageService, RdTranslatePipe, StoredRequest, StoredResource } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';

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

type Strip = 'all' | 'free' | 'busy' | 'notUpdated';
type Bucket = 'free' | 'busy' | 'notUpdated';

const CLOSED = new Set(['completed', 'resolved', 'closed']);
/** A check-in older than this is "Not updated". */
const CHECKIN_MIN = 120;
const DISTANCE_CAP_KM = 50;

/** Great-circle kilometres, rounded like the case-card distance. */
function distanceKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const radius = 6371;
  const p1 = (lat1 * Math.PI) / 180;
  const p2 = (lat2 * Math.PI) / 180;
  const dPhi = ((lat2 - lat1) * Math.PI) / 180;
  const dLambda = ((lng2 - lng1) * Math.PI) / 180;
  const a = Math.sin(dPhi / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dLambda / 2) ** 2;
  const raw = radius * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(raw * 100) / 100;
}

@Component({
  selector: 'app-coordinator-teams',
  standalone: true,
  imports: [CommonModule, RouterLink, RdTranslatePipe, MapProviderComponent],
  templateUrl: './coordinator-teams.component.html',
  styleUrl: './coordinator-teams.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorTeamsComponent implements OnInit {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);

  readonly resources = signal<StoredResource[]>([]);
  readonly requests = signal<StoredRequest[]>([]);
  readonly strip = signal<Strip>('all');
  readonly openId = signal<string | null>(null);
  readonly now = signal(Date.now());
  readonly notice = signal('');

  readonly counts = computed(() => {
    const rows = this.resources();
    return {
      free: rows.filter((team) => this.bucket(team) === 'free').length,
      busy: rows.filter((team) => this.bucket(team) === 'busy').length,
      notUpdated: rows.filter((team) => this.bucket(team) === 'notUpdated').length,
    };
  });

  readonly filtered = computed(() => {
    const mode = this.strip();
    const rankOf = (team: StoredResource) => ({ free: 0, notUpdated: 1, busy: 2 }[this.bucket(team)]);
    const rows = this.resources().filter((team) => mode === 'all' || this.bucket(team) === mode);
    return [...rows].sort((a, b) => rankOf(a) - rankOf(b) || a.name.localeCompare(b.name));
  });

  ngOnInit(): void {
    this.api.getResources().subscribe({
      next: (rows) => this.resources.set(rows),
      error: () => this.resources.set([]),
    });
    this.api.getRequests().subscribe({
      next: (rows) => this.requests.set(rows),
      error: () => this.requests.set([]),
    });
  }

  setStrip(mode: Exclude<Strip, 'all'>): void {
    this.strip.set(this.strip() === mode ? 'all' : mode);
  }

  toggle(id: string): void {
    this.openId.set(this.openId() === id ? null : id);
  }

  /** On a case, otherwise free. A missed check-in is never free. */
  bucket(team: StoredResource): Bucket {
    if (this.onCase(team)) return 'busy';
    if (this.checkInLate(team)) return 'notUpdated';
    return 'free';
  }

  onCase(team: StoredResource): boolean {
    if (team.assigned_request_id) return true;
    return team.status === 'busy' || team.status === 'dispatched' || team.status === 'en_route' || team.status === 'on_scene';
  }

  /** No check-in, or the last one is over 2 hours old. */
  checkInLate(team: StoredResource): boolean {
    const minutes = this.minutesAgo(team);
    return minutes == null || minutes > CHECKIN_MIN;
  }

  statusLabel(team: StoredResource): string {
    const key = { free: 'coord.teamFree', busy: 'coord.teamBusy', notUpdated: 'coord.notUpdated' }[this.bucket(team)];
    return this.lang.translate(key);
  }

  kindLabel(kind: string): string {
    return this.lang.translate(`coord.kind.${kind}`);
  }

  area(team: StoredResource): string {
    return team.area_name || AREAS[team.ward_id] || team.ward_id;
  }

  /** Kilometres to the nearest open case. Anything past 50 km is shown as the cap. */
  leg(team: StoredResource): string {
    this.lang.currentLang();
    const open = this.requests().filter((row) => row.lat != null && row.lng != null && !row.merged_into && !CLOSED.has(row.status));
    if (!open.length) return this.area(team);
    const km = Math.min(...open.map((row) => distanceKm(row.lat as number, row.lng as number, team.lat, team.lng)));
    if (km > DISTANCE_CAP_KM) return this.lang.translate('coord.distanceCap');
    const minutes = Math.max(1, Math.round((km / 20) * 60));
    const eta = this.lang.translate('coord.etaMin').replace('{n}', String(minutes));
    return `${km} km · ${eta}`;
  }

  /** Every team. The map frames this set, not a single case. */
  readonly teamPins = computed<MapPin[]>(() => this.resources().map((team) => ({
    id: team.id,
    lat: team.lat,
    lng: team.lng,
    title: team.name,
  })));

  readonly mapCenter = computed(() => {
    const pins = this.teamPins();
    if (!pins.length) return { lat: 9.47, lng: 76.39 };
    return {
      lat: pins.reduce((sum, pin) => sum + pin.lat, 0) / pins.length,
      lng: pins.reduce((sum, pin) => sum + pin.lng, 0) / pins.length,
    };
  });

  /** Minutes since the last check-in, or null when the team has never checked in. */
  minutesAgo(team: StoredResource): number | null {
    this.now();
    const stamp = team.location_updated_at || '';
    if (!stamp) return null;
    return Math.max(0, Math.round((Date.now() - new Date(stamp).getTime()) / 60000));
  }

  ageLabel(team: StoredResource): string {
    const m = this.minutesAgo(team);
    if (m == null) return this.lang.translate('coord.notUpdated');
    const key = m < 60 ? 'coord.updatedMin' : 'coord.updatedHour';
    const n = m < 60 ? m : Math.round(m / 60);
    return this.lang.translate(key).replace('{n}', String(n));
  }

  seats(team: StoredResource): string {
    return this.lang.translate('coord.teamSeats')
      .replace('{free}', String(team.capacity_remaining))
      .replace('{n}', String(team.capacity_total));
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
    return ({ boat: 'var(--brand)', medical: 'var(--sev-crit)', food: 'var(--sev-high)', shelter: 'var(--ok)' } as Record<string, string>)[kind] || 'var(--brand)';
  }
}
