import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Router, RouterModule } from '@angular/router';
import { ApiClientService, PublicCell, PublicAlert, RdTranslatePipe } from '@rd/shared';
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
