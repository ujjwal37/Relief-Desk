import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiClientService, LanguageService, MatchProposal, RdTranslatePipe, StoredRequest, StoredResource, urgencyBand } from '@rd/shared';
import { MapLeg, MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { CHECKIN_LATE_MIN, haversineKm, legTitle, quoteFromProposal, teamTone, TravelQuote } from '../../../core/maps/map-markers';
import { teamBucket, teamsFreeCounts } from '../../team-status';
import { CoordUiService } from '../../../core/services/coord-ui.service';
import { DeskStore } from '../../../core/desk-store';

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
  private ui = inject(CoordUiService);
  private desk = inject(DeskStore);

  readonly resources = this.desk.resources;
  readonly requests = signal<StoredRequest[]>([]);
  readonly matches = signal<MatchProposal[]>([]);
  readonly strip = signal<Strip>('all');
  readonly openId = signal<string | null>(null);
  readonly highlightId = signal<string | null>(null);
  readonly now = signal(Date.now());
  readonly notice = signal('');

  constructor() {
    effect((onCleanup) => {
      const id = this.ui.selectedCaseId();
      if (!id) {
        this.matches.set([]);
        return;
      }
      const sub = this.api.getRequestMatches(id, 5).subscribe({
        next: (rows) => this.matches.set(rows),
        error: () => this.matches.set([]),
      });
      onCleanup(() => sub.unsubscribe());
    });
    effect(() => {
      if (!this.desk.casesReady()) return;
      this.requests.set(this.desk.requests());
    });
  }

  readonly counts = computed(() => {
    const { free, busy, notUpdated } = teamsFreeCounts(this.resources(), this.now());
    return { free, busy, notUpdated };
  });

  readonly filtered = computed(() => {
    const mode = this.strip();
    const rankOf = (team: StoredResource) => ({ free: 0, notUpdated: 1, busy: 2 }[this.bucket(team)]);
    const rows = this.resources().filter((team) => mode === 'all' || this.bucket(team) === mode);
    return [...rows].sort((a, b) => rankOf(a) - rankOf(b) || a.name.localeCompare(b.name));
  });

  ngOnInit(): void {
    this.api.getResources().subscribe({
      next: (rows) => this.desk.resources.set(rows),
      error: () => this.desk.resources.set([]),
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
    const next = this.openId() === id ? null : id;
    this.openId.set(next);
    this.highlightId.set(next);
    if (!next || typeof document === 'undefined') return;
    queueMicrotask(() => document.querySelector('[data-testid="team-detail"]')?.scrollIntoView({ block: 'nearest' }));
  }

  /** A team pin on the map opens that row, the same as clicking it in the list. */
  pickTeamPin(id: string): void {
    if (this.resources().some((row) => row.id === id)) this.toggle(id);
  }

  bucket(team: StoredResource): Bucket {
    return teamBucket(team, this.now());
  }

  onCase(team: StoredResource): boolean {
    if (team.assigned_request_id) return true;
    return team.status === 'busy' || team.status === 'dispatched' || team.status === 'en_route' || team.status === 'on_scene';
  }

  /** No check-in, or the last one is over 2 hours old. A team on a case can still be late on the clock. */
  checkInLate(team: StoredResource): boolean {
    const minutes = this.minutesAgo(team);
    return minutes == null || minutes > CHECKIN_LATE_MIN;
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

  /** Busy teams: On {INC} · {d} km. Otherwise the candidate line or nearest open case. */
  leg(team: StoredResource): string {
    this.lang.currentLang();
    if (this.bucket(team) === 'busy' && team.assigned_request_id) {
      const req = this.requests().find((row) => row.id === team.assigned_request_id);
      const km = req?.lat != null && req.lng != null
        ? Math.min(50, haversineKm(req.lat, req.lng, team.lat, team.lng))
        : 0;
      return this.lang.translate('coord.onCaseKm').replace('{id}', team.assigned_request_id).replace('{d}', String(km));
    }
    const drawn = this.teamLegs().find((row) => row.id === team.id);
    if (drawn) return drawn.title;
    const quote = this.nearestQuote(team);
    if (!quote) return this.area(team);
    // Name the case the distance is to, so it is never read as the distance to a different case.
    const near = this.nearestCase(team);
    const title = legTitle(quote, (key) => this.lang.translate(key));
    return near ? this.lang.translate('coord.bestFor').replace('{id}', near.public_code || near.id) : title;
  }

  private nearestCase(team: StoredResource): StoredRequest | null {
    const open = this.requests().filter((row) => row.lat != null && row.lng != null && !row.merged_into && !CLOSED.has(row.status));
    return [...open].sort((a, b) => haversineKm(a.lat as number, a.lng as number, team.lat, team.lng) - haversineKm(b.lat as number, b.lng as number, team.lat, team.lng))[0] ?? null;
  }

  private nearestQuote(team: StoredResource): TravelQuote | null {
    const open = this.requests().filter((row) => row.lat != null && row.lng != null && !row.merged_into && !CLOSED.has(row.status));
    if (!open.length) return null;
    const km = Math.min(...open.map((row) => haversineKm(row.lat as number, row.lng as number, team.lat, team.lng)));
    return { km, teamAvailable: team.status === 'available' };
  }

  /** The selected team's case: its assignment, else the nearest open case. */
  readonly teamTarget = computed<StoredRequest | null>(() => {
    const team = this.resources().find((row) => row.id === this.openId());
    if (!team || team.lat == null || team.lng == null) return null;
    const placed = this.requests().filter((row) => row.lat != null && row.lng != null && !row.merged_into);
    const assigned = team.assigned_request_id ? placed.find((row) => row.id === team.assigned_request_id) : undefined;
    if (assigned) return assigned;
    const open = placed.filter((row) => !CLOSED.has(row.status));
    return [...open].sort((a, b) => haversineKm(a.lat as number, a.lng as number, team.lat, team.lng) - haversineKm(b.lat as number, b.lng as number, team.lat, team.lng))[0] ?? null;
  });

  /** Every team, plus the open case when one is selected. */
  readonly teamPins = computed<MapPin[]>(() => {
    const pins: MapPin[] = this.resources().map((team) => ({
      id: team.id,
      lat: team.lat,
      lng: team.lng,
      title: team.name,
      marker: 'team' as const,
      vehicle: team.kind,
      tone: teamTone(team, this.now()),
    }));
    const req = this.openId() ? this.teamTarget() : this.requests().find((row) => row.id === this.ui.selectedCaseId());
    if (req?.lat != null && req.lng != null) {
      pins.unshift({
        id: req.id,
        lat: req.lat,
        lng: req.lng,
        title: req.place_text || req.id,
        marker: 'case',
        tone: urgencyBand(req.urgency_score),
      });
    }
    return pins;
  });

  /** Top three candidates for the open case. Empty until a case is selected. */
  readonly teamLegs = computed<MapLeg[]>(() => {
    this.lang.currentLang();
    const picked = this.resources().find((row) => row.id === this.openId());
    if (picked) {
      const target = this.teamTarget();
      if (!target || target.lat == null || target.lng == null) return [];
      const prop = this.matches().find((row) => row.resource_id === picked.id);
      const quote = prop
        ? quoteFromProposal(prop, picked.status === 'available')
        : { km: haversineKm(target.lat, target.lng, picked.lat, picked.lng), teamAvailable: picked.status === 'available', water: picked.kind === 'boat' };
      return [{
        id: picked.id,
        from: { lat: target.lat, lng: target.lng },
        to: { lat: picked.lat, lng: picked.lng },
        title: legTitle(quote, (key) => this.lang.translate(key)),
        suggested: true,
        mode: picked.kind === 'boat' ? 'water' : 'road',
      }];
    }
    const req = this.requests().find((row) => row.id === this.ui.selectedCaseId());
    if (!req || req.lat == null || req.lng == null) return [];
    const suggested = this.matches()[0]?.resource_id;
    const legs: MapLeg[] = [];
    for (const prop of this.matches().slice(0, 3)) {
      const team = this.resources().find((row) => row.id === prop.resource_id);
      if (!team) continue;
      legs.push({
        id: team.id,
        from: { lat: req.lat, lng: req.lng },
        to: { lat: team.lat, lng: team.lng },
        title: legTitle(quoteFromProposal(prop, team.status === 'available'), (key) => this.lang.translate(key)),
        suggested: team.id === suggested,
        mode: team.kind === 'boat' ? 'water' : 'road',
      });
    }
    return legs;
  });

  readonly legendKinds = computed(() => {
    const present = new Set(this.teamPins().map((pin) => pin.vehicle).filter((kind): kind is NonNullable<typeof kind> => !!kind));
    return (['boat', 'medical', 'food', 'shelter'] as const).filter((kind) => present.has(kind));
  });

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
