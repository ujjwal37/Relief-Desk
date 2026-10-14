import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { ApiClientService, LanguageService, PublicCell, PublicAlert, RdTranslatePipe } from '@rd/shared';
import { MapPin, MapProviderComponent } from '../../../core/maps/map-provider.component';

@Component({
  selector: 'app-nearby',
  standalone: true,
  imports: [CommonModule, RouterModule, MapProviderComponent, RdTranslatePipe],
  templateUrl: './nearby.component.html',
  styleUrls: ['./nearby.component.scss'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NearbyComponent implements OnInit {
  private api = inject(ApiClientService);
  private router = inject(Router);
  private lang = inject(LanguageService);

  cells = signal<PublicCell[]>([]);
  alerts = signal<PublicAlert[]>([]);
  readonly mapPins = computed<MapPin[]>(() =>
    this.cells().map((cell) => ({
      id: cell.cell_id,
      lat: cell.center_lat,
      lng: cell.center_lng,
      title: cell.ward,
    })),
  );
  selectedCell = signal<PublicCell | null>(null);
  isLoading = signal(true);
  distanceFilter = signal('3 km');

  ngOnInit(): void {
    this.loadData();
  }

  loadData(): void {
    this.isLoading.set(true);

    this.api.getPublicCells().subscribe({
      next: (res) => {
        this.cells.set(res.cells);
        if (res.cells.length > 0) {
          this.selectedCell.set(res.cells[0]);
        }
        this.isLoading.set(false);
      },
      error: (err) => {
        console.warn('Failed to load cells, falling back to local dataset', err);
        this.isLoading.set(false);
      }
    });

    this.api.getPublicAlerts().subscribe({
      next: (alerts) => {
        this.alerts.set(alerts);
      },
      error: (err) => {
        console.warn('Failed to load public alerts', err);
      }
    });
  }

  private local(key: string, fallback: string): string {
    this.lang.currentLang();
    const text = this.lang.translate(key);
    return text === key ? fallback : text;
  }

  alertTitle(alert: PublicAlert): string {
    return this.local(`nearby.card.${alert.id}.title`, alert.title);
  }

  alertBody(alert: PublicAlert): string {
    return this.local(`nearby.card.${alert.id}.desc`, alert.description);
  }

  alertWhen(alert: PublicAlert): string {
    return this.local(`nearby.card.${alert.id}.ago`, alert.time_ago);
  }

  bucketLabel(text: string): string {
    if (text === 'Last 2 hours') return this.local('nearby.bucket2', text);
    if (text === 'Last 3 hours') return this.local('nearby.bucket3', text);
    return text;
  }

  hazardLabel(cell: PublicCell): string {
    return this.local(`nearby.hazard.${cell.cell_id}`, cell.active_hazard || '');
  }

  selectCell(cell: PublicCell): void {
    this.selectedCell.set(cell);
  }

  onMapPin(id: string): void {
    const cell = this.cells().find((item) => item.cell_id === id);
    if (cell) {
      this.selectCell(cell);
    }
  }

  navigateTo(path: string): void {
    this.router.navigate([path]);
  }
}
