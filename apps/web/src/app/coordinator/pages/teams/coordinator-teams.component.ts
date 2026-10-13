import { ChangeDetectionStrategy, Component, OnInit, computed, effect, inject, signal, untracked } from '@angular/core';
import { CommonModule } from '@angular/common';
import { RouterLink } from '@angular/router';
import { ApiClientService, LanguageService, MatchProposal, RdTranslatePipe, StoredRequest, StoredResource } from '@rd/shared';
import { MapLeg, MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { CoordUiService } from '../../../core/services/coord-ui.service';

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

type Strip = 'all' | 'free' | 'busy';

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
  private ui = inject(CoordUiService);

  readonly resources = signal<StoredResource[]>([]);
  readonly requests = signal<StoredRequest[]>([]);
  readonly matches = signal<MatchProposal[]>([]);
  readonly strip = signal<Strip>('all');
  readonly openId = signal<string | null>(null);
  readonly now = signal(Date.now());
  readonly notice = signal('');
  /** Bumped when the open case changes so Google pans even if the centre is unchanged. */
  readonly focusToken = signal(0);

  readonly counts = computed(() => {
    const rows = this.resources();
    return {
      free: rows.filter((team) => this.isFree(team)).length,
      busy: rows.filter((team) => !this.isFree(team)).length,
    };
  });

  readonly focus = computed(() => {
    const id = this.ui.selectedCaseId();
    if (!id) return undefined;
    return this.requests().find((row) => row.id === id);
  });

  readonly filtered = computed(() => {
    const mode = this.strip();
    const rows = this.resources().filter((team) => {
      if (mode === 'free') return this.isFree(team);
      if (mode === 'busy') return !this.isFree(team);
      return true;
    });
    return [...rows].sort((a, b) => {
      const rank = Number(!this.isFree(a)) - Number(!this.isFree(b));
      if (rank !== 0) return rank;
      return a.name.localeCompare(b.name);
    });
  });

  constructor() {
    let seen = '';
    effect(() => {
      const id = this.ui.selectedCaseId();
      if (id === seen) return;
      seen = id;
      untracked(() => this.focusToken.update((n) => n + 1));
    });
  }

  ngOnInit(): void {
    this.api.getResources().subscribe({
      next: (rows) => this.resources.set(rows),
      error: () => this.resources.set([]),
    });
    this.api.getRequests().subscribe({
      next: (rows) => {
        this.requests.set(rows);
        if (!this.ui.selectedCaseId()) {
          const open = rows.filter((row) => !row.merged_into && row.status !== 'completed' && row.status !== 'resolved' && row.status !== 'closed');
          const pick = [...open].sort((a, b) => (b.urgency_score || 0) - (a.urgency_score || 0))[0];
          if (pick) this.ui.selectedCaseId.set(pick.id);
        }
        this.loadMatches();
      },
      error: () => this.requests.set([]),
    });
  }

  private loadMatches(): void {
    const id = this.ui.selectedCaseId();
    if (!id) {
      this.matches.set([]);
      return;
    }
    this.api.getRequestMatches(id, 5).subscribe({
      next: (rows) => this.matches.set(rows),
      error: () => this.matches.set([]),
    });
  }

  setStrip(mode: Exclude<Strip, 'all'>): void {
    this.strip.set(this.strip() === mode ? 'all' : mode);
  }

  toggle(id: string): void {
    this.openId.set(this.openId() === id ? null : id);
  }

  isFree(team: StoredResource): boolean {
    return team.status === 'available';
  }

  statusKey(team: StoredResource): string {
    if (team.status === 'busy') return 'dispatched';
    return team.status;
  }

  statusLabel(team: StoredResource): string {
    return this.lang.translate(`coord.resStatus.${this.statusKey(team)}`);
  }

  kindLabel(kind: string): string {
    return this.lang.translate(`coord.kind.${kind}`);
  }

  area(team: StoredResource): string {
    return team.area_name || AREAS[team.ward_id] || team.ward_id;
  }

  /** Distance and ETA to the open case. "No nearby team" stays on the case card only. */
  leg(team: StoredResource): string {
    this.lang.currentLang();
    const req = this.focus();
    if (req?.lat == null || req?.lng == null) return this.area(team);
    const quoted = this.matches().find((row) => row.resource_id === team.id);
    const km = quoted?.breakdown?.distance_km ?? distanceKm(req.lat, req.lng, team.lat, team.lng);
    const minutes = quoted?.eta_minutes ?? Math.max(1, Math.round((km / 20) * 60));
    const eta = this.lang.translate('coord.etaMin').replace('{n}', String(minutes));
    return `${km} km · ${eta}`;
  }

  /** Every team, plus the open case, in real coordinates. */
  readonly teamPins = computed<MapPin[]>(() => {
    const pins: MapPin[] = this.resources().map((team) => ({
      id: team.id,
      lat: team.lat,
      lng: team.lng,
      title: team.name,
    }));
    const req = this.focus();
    if (req?.lat != null && req.lng != null) {
      pins.unshift({ id: req.id, lat: req.lat, lng: req.lng, title: req.place_text || req.id });
    }
    return pins;
  });

  /** Lines from the open case to the teams the matcher suggested. The first is the suggested team. */
  readonly teamLegs = computed<MapLeg[]>(() => {
    const req = this.focus();
    if (!req || req.lat == null || req.lng == null) return [];
    const suggested = this.matches()[0]?.resource_id;
    const legs: MapLeg[] = [];
    for (const prop of this.matches()) {
      const team = this.resources().find((row) => row.id === prop.resource_id);
      if (!team) continue;
      legs.push({
        id: prop.resource_id,
        from: { lat: req.lat, lng: req.lng },
        to: { lat: team.lat, lng: team.lng },
        title: this.leg(team),
        suggested: prop.resource_id === suggested,
      });
    }
    return legs;
  });

  readonly mapCenter = computed(() => {
    const req = this.focus();
    if (req?.lat != null && req.lng != null) return { lat: req.lat, lng: req.lng };
    return { lat: 9.47, lng: 76.39 };
  });

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
