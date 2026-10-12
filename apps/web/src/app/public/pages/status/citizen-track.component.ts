import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, CitizenTrack, LanguageService, RdTranslatePipe } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';

@Component({
  selector: 'app-citizen-track',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe, MapProviderComponent],
  templateUrl: './citizen-track.component.html',
  styleUrl: './citizen-track.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CitizenTrackComponent implements OnInit, OnDestroy {
  private api = inject(ApiClientService);
  private lang = inject(LanguageService);

  readonly reportId = input.required<string>();
  readonly token = input<string>('');

  readonly data = signal<CitizenTrack | null>(null);
  private timer: ReturnType<typeof setInterval> | null = null;

  readonly line = computed(() => {
    this.lang.currentLang();
    const row = this.data();
    if (!row?.visible) return this.lang.translate('track.waiting');
    if (row.state === 'arrived') {
      return `${row.team_name || ''}`.trim()
        ? `${row.team_name}. ${this.lang.translate('track.arrived')}`
        : this.lang.translate('track.arrived');
    }
    if (row.state === 'completed') return this.lang.translate('track.completed');
    if (row.no_nearby || row.eta_minutes == null || row.distance_km == null) {
      return this.lang.translate('track.noNearby');
    }
    return this.lang.translate('track.away')
      .replace('{name}', row.team_name || '')
      .replace('{km}', String(row.distance_km))
      .replace('{min}', String(row.eta_minutes));
  });

  readonly center = computed(() => {
    const row = this.data();
    if (row?.lat != null && row.lng != null) return { lat: row.lat, lng: row.lng };
    return { lat: 10.2, lng: 76.3 };
  });

  readonly pins = computed<MapPin[]>(() => {
    const row = this.data();
    if (!row?.visible || row.lat == null || row.lng == null) return [];
    const pins: MapPin[] = [{ id: 'team', lat: row.lat, lng: row.lng, title: row.team_name || '' }];
    if (row.case_lat != null && row.case_lng != null) {
      pins.push({ id: 'case', lat: row.case_lat, lng: row.case_lng, title: '' });
    }
    return pins;
  });

  readonly svg = computed(() => {
    const row = this.data();
    if (!row?.visible || row.lat == null || row.lng == null) return null;
    const points = [
      { id: 'team', lat: row.lat, lng: row.lng },
      ...(row.case_lat != null && row.case_lng != null ? [{ id: 'case', lat: row.case_lat, lng: row.case_lng }] : []),
      ...(row.trail || []),
    ];
    const lats = points.map((p) => p.lat);
    const lngs = points.map((p) => p.lng);
    const minLa = Math.min(...lats);
    const maxLa = Math.max(...lats);
    const minLo = Math.min(...lngs);
    const maxLo = Math.max(...lngs);
    const project = (lat: number, lng: number) => ({
      x: 16 + ((lng - minLo) / Math.max(1e-6, maxLo - minLo)) * 248,
      y: 16 + (1 - (lat - minLa) / Math.max(1e-6, maxLa - minLa)) * 128,
    });
    const team = project(row.lat, row.lng);
    const place = row.case_lat != null && row.case_lng != null ? project(row.case_lat, row.case_lng) : null;
    const trail = (row.trail || []).map((p) => {
      const at = project(p.lat, p.lng);
      return `${at.x.toFixed(1)},${at.y.toFixed(1)}`;
    }).join(' ');
    return { team, place, trail };
  });

  ngOnInit(): void {
    this.load();
    this.timer = setInterval(() => this.load(), 10000);
  }

  ngOnDestroy(): void {
    if (this.timer) clearInterval(this.timer);
  }

  updatedLabel(): string {
    const stamp = this.data()?.updated_at;
    if (!stamp) return '';
    const parsed = new Date(stamp);
    if (Number.isNaN(parsed.getTime())) return '';
    return this.lang.translate('track.updated').replace('{time}', parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));
  }

  private load(): void {
    const id = this.reportId();
    const token = this.token();
    if (!id || !token) return;
    this.api.getCitizenTrack(id, token).subscribe({
      next: (row) => this.data.set(row),
      error: () => this.data.set(null),
    });
  }
}
