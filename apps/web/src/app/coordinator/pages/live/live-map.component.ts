import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, LanguageService, RdTranslatePipe, StoredRequest, TeamLive, urgencyBand } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';
import { MapLegendComponent } from '../../../core/maps/map-legend.component';
import { MapPinDirective } from '../../../core/maps/map-pin.directive';
import {
  PinSpec,
  RELIEF_PLACES,
  caseTitle,
  pinCopy,
  pinZ,
  placeTitle,
  teamGlyph,
  teamTitle,
} from '../../../core/maps/map-pins';

const KERALA = { minLa: 9.2, maxLa: 11.9, minLo: 75.85, maxLo: 76.85 };
const DISTRICTS = [
  { id: 'alappuzha', ring: [[9.34, 76.30], [9.34, 76.55], [9.70, 76.52], [9.72, 76.31]] },
  { id: 'ernakulam', ring: [[9.90, 76.18], [9.95, 76.72], [10.28, 76.70], [10.22, 76.16]] },
  { id: 'thrissur', ring: [[10.15, 76.02], [10.18, 76.48], [10.62, 76.42], [10.58, 76.02]] },
  { id: 'wayanad', ring: [[11.42, 75.95], [11.46, 76.28], [11.78, 76.24], [11.74, 75.96]] },
];

@Component({
  selector: 'app-live-map',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe, MapProviderComponent, MapLegendComponent, MapPinDirective],
  templateUrl: './live-map.component.html',
  styleUrl: './live-map.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LiveMapComponent implements OnInit, OnDestroy {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);

  readonly teams = signal<TeamLive[]>([]);
  readonly cases = signal<StoredRequest[]>([]);
  readonly selectedTeamId = signal<string | null>(null);
  readonly selectedCaseId = signal<string | null>(null);
  readonly notice = signal('');
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly frame = computed(() => {
    const points = this.cases()
      .filter((row) => row.lat != null && row.lng != null && this.inKerala(row.lat as number, row.lng as number))
      .map((row) => ({ lat: row.lat as number, lng: row.lng as number }));
    if (!points.length) return KERALA;
    const minLa = Math.min(...points.map((p) => p.lat));
    const maxLa = Math.max(...points.map((p) => p.lat));
    const minLo = Math.min(...points.map((p) => p.lng));
    const maxLo = Math.max(...points.map((p) => p.lng));
    const padLa = Math.max(0.08, (maxLa - minLa) * 0.18);
    const padLo = Math.max(0.08, (maxLo - minLo) * 0.18);
    return { minLa: minLa - padLa, maxLa: maxLa + padLa, minLo: minLo - padLo, maxLo: maxLo + padLo };
  });

  readonly districts = computed(() => DISTRICTS.map((district) => {
    const pts = district.ring.map(([lat, lng]) => this.project(lat, lng));
    return {
      id: district.id,
      points: pts.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '),
      lx: pts.reduce((sum, p) => sum + p.x, 0) / pts.length,
      ly: pts.reduce((sum, p) => sum + p.y, 0) / pts.length,
    };
  }));

  readonly drawn = computed(() => this.teams().map((team) => {
    const at = this.project(team.lat, team.lng);
    const trail = (team.trail || []).map((point) => {
      const spot = this.project(point.lat, point.lng);
      return `${spot.x.toFixed(1)},${spot.y.toFixed(1)}`;
    }).join(' ');
    const linked = team.case_lat != null && team.case_lng != null ? this.project(team.case_lat, team.case_lng) : null;
    return { ...team, x: at.x, y: at.y, trail, linked };
  }));

  readonly casePins = computed(() => this.cases()
    .filter((row) => row.lat != null && row.lng != null && !this.isDone(row))
    .map((row) => ({ ...row, ...this.project(row.lat as number, row.lng as number) })));

  readonly markerPins = computed(() => {
    this.lang.currentLang();
    const copy = pinCopy((key) => this.lang.translate(key));
    const selected = this.selectedCaseId();
    const pins: { id: string; x: number; y: number; lat: number; lng: number; title: string; dim: boolean; spec: PinSpec; z: number }[] = [];
    this.casePins().forEach((row, index) => {
      const severity = urgencyBand(row.urgency_score || 0);
      const merged = row.merged_count || 1;
      const spec: PinSpec = { kind: 'case', severity, queue: index + 1, merged, selected: row.id === selected };
      pins.push({
        id: row.id,
        x: row.x,
        y: row.y,
        lat: row.lat as number,
        lng: row.lng as number,
        title: caseTitle(index + 1, severity, merged, copy),
        dim: !!selected && row.id !== selected,
        spec,
        z: pinZ(spec),
      });
    });
    for (const team of this.drawn()) {
      const free = team.status === 'available' && !team.stale;
      const glyph = teamGlyph(team.kind, team.name);
      const spec: PinSpec = { kind: 'team', team: glyph, free };
      pins.push({
        id: team.id,
        x: team.x,
        y: team.y,
        lat: team.lat,
        lng: team.lng,
        title: teamTitle(glyph, team.name, free, !!team.stale, copy),
        dim: !!selected,
        spec,
        z: pinZ(spec),
      });
    }
    for (const place of RELIEF_PLACES) {
      const at = this.project(place.lat, place.lng);
      const spec: PinSpec = { kind: 'place', place: place.place, label: place.name };
      pins.push({
        id: place.id,
        x: at.x,
        y: at.y,
        lat: place.lat,
        lng: place.lng,
        title: placeTitle(place.place, place.name, copy),
        dim: !!selected,
        spec,
        z: pinZ(spec),
      });
    }
    return pins.sort((a, b) => a.z - b.z);
  });

  readonly pins = computed<MapPin[]>(() => this.markerPins().map((pin) => ({
    id: pin.id,
    lat: pin.lat,
    lng: pin.lng,
    title: pin.title,
    spec: pin.spec,
    dim: pin.dim,
    zIndex: pin.z,
  })));

  readonly center = computed(() => {
    const frame = this.frame();
    return { lat: (frame.minLa + frame.maxLa) / 2, lng: (frame.minLo + frame.maxLo) / 2 };
  });

  ngOnInit(): void {
    this.reload();
    this.timer = setInterval(() => this.reload(), 5000);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  reload(): void {
    this.api.getTeamLocations().subscribe({
      next: (body) => this.teams.set(body.teams || []),
      error: () => this.teams.set([]),
    });
    this.api.getRequests().subscribe({
      next: (rows) => this.cases.set(rows || []),
      error: () => this.cases.set([]),
    });
  }

  selectTeam(id: string): void {
    const team = this.teams().find((row) => row.id === id);
    this.selectedTeamId.set(id);
    this.selectedCaseId.set(team?.assigned_request_id || null);
  }

  selectCase(id: string): void {
    const team = this.teams().find((row) => row.assigned_request_id === id);
    this.selectedCaseId.set(id);
    this.selectedTeamId.set(team?.id || null);
  }

  onPin(id: string): void {
    if (this.teams().some((row) => row.id === id)) this.selectTeam(id);
    else this.selectCase(id);
  }

  etaLabel(team: TeamLive): string {
    this.lang.currentLang();
    if (team.no_nearby || team.eta_minutes == null) return this.lang.translate('track.noNearby');
    return this.lang.translate('track.eta').replace('{n}', String(team.eta_minutes));
  }

  statusLabel(status: string): string {
    const key = status === 'dispatched' || status === 'busy' ? 'busy'
      : status === 'en_route' ? 'onTheWay'
      : status === 'on_scene' ? 'arrived'
      : status === 'available' ? 'free'
      : status === 'off_duty' ? 'offDuty'
      : status === 'accepted' ? 'accepted'
      : 'free';
    return this.lang.translate(`track.status.${key}`);
  }

  busyLabel(team: TeamLive): string {
    if (team.busy_minutes == null) return '';
    return this.lang.translate('track.busyFor').replace('{n}', String(team.busy_minutes));
  }

  sourceLabel(team: TeamLive): string {
    if (team.simulated || team.source === 'simulated') return this.lang.translate('track.simulated');
    if (team.source === 'gps') return this.lang.translate('track.liveGps');
    return this.lang.translate('track.base');
  }

  override(team: TeamLive, event: Event): void {
    event.preventDefault();
    const form = event.target as HTMLFormElement;
    const data = new FormData(form);
    const status = String(data.get('status') || '');
    const reason = String(data.get('reason') || '');
    this.api.overrideTeamStatus(team.id, status, reason).subscribe({
      next: () => {
        this.notice.set(this.lang.translate('team.saved'));
        this.reload();
      },
    });
  }

  project(lat: number, lng: number): { x: number; y: number } {
    const frame = this.frame();
    return {
      x: 36 + ((lng - frame.minLo) / Math.max(1e-6, frame.maxLo - frame.minLo)) * 528,
      y: 28 + (1 - (lat - frame.minLa) / Math.max(1e-6, frame.maxLa - frame.minLa)) * 424,
    };
  }

  private inKerala(lat: number, lng: number): boolean {
    return lat >= 8 && lat <= 13 && lng >= 74 && lng <= 78;
  }

  private isDone(row: StoredRequest): boolean {
    return row.status === 'completed' || row.status === 'resolved' || row.status === 'closed';
  }
}
