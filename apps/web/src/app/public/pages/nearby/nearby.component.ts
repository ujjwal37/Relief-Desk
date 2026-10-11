import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-nearby',
  standalone: true,
  template: `
    <div class="nearby-card">
      <h2>Area Incidents (Area-Level Only)</h2>
      <p class="subtitle">Aggregated grid cells only. No personal identifying information.</p>
      <div class="map-placeholder">
        <div class="pin-info">
          <span>📍 Ward 3: Riverfront Ghat</span>
          <span class="badge critical">Flood Level: High</span>
        </div>
        <div class="pin-info">
          <span>📍 Ward 12: Lake View</span>
          <span class="badge medium">Waterlogging</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .nearby-card {
      background: white; padding: 20px; border-radius: 16px; border: 1px solid #e2e8f0;
      h2 { margin: 0 0 6px; font-size: 1.25rem; }
      .subtitle { margin: 0 0 16px; color: #64748b; font-size: 0.85rem; }
      .map-placeholder {
        height: 280px; background: #f1f5f9; border-radius: 12px; display: flex; flex-direction: column;
        justify-content: center; align-items: center; gap: 12px;
        .pin-info {
          background: white; padding: 8px 14px; border-radius: 8px; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
          display: flex; gap: 10px; align-items: center; font-size: 0.875rem;
          .badge {
            font-size: 0.75rem; padding: 2px 8px; border-radius: 4px; font-weight: 700;
            &.critical { background: #fee2e2; color: #dc2626; }
            &.medium { background: #fef3c7; color: #d97706; }
          }
        }
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class NearbyComponent {}
