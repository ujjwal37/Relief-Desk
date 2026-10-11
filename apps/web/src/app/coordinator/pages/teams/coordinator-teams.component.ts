import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ApiClientService, LanguageService, RdTranslatePipe, StoredResource } from '@rd/shared';

const AREAS: Record<string, string> = {
  ward_1: 'Sangam Vihar',
  ward_2: 'Gandhi Nagar',
  ward_3: 'Riverfront Ghat',
  ward_4: 'Old Bazaar',
  ward_5: 'Shanti Nagar',
  ward_6: 'Civil Lines',
  ward_7: 'Industrial Area',
  ward_8: 'Green Park',
  ward_9: 'Subhash Nagar',
  ward_10: 'Model Town',
  ward_11: 'Transport Nagar',
  ward_12: 'Lake View',
};

@Component({
  selector: 'app-coordinator-teams',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  templateUrl: './coordinator-teams.component.html',
  styleUrl: './coordinator-teams.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorTeamsComponent implements OnInit {
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

  ngOnInit(): void {
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
    return this.lang.translate(`coord.resStatus.${this.statusKey(team)}`);
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
