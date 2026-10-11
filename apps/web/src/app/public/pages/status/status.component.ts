import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-status',
  standalone: true,
  template: `
    <div class="status-card">
      <h2>Request Tracking</h2>
      <p class="subtitle">Enter your Request ID to track assistance progress.</p>
      <div class="input-group">
        <input type="text" placeholder="e.g. REQ-1042" />
        <button class="track-btn">Track</button>
      </div>
      <div class="status-steps">
        <div class="step completed">1. Received / प्राप्त</div>
        <div class="step active">2. Matched / मिलान हुआ</div>
        <div class="step">3. Dispatch Approved / सहायता रवाना</div>
      </div>
    </div>
  `,
  styles: [`
    .status-card {
      background: white;
      padding: 24px;
      border-radius: 16px;
      border: 1px solid #e2e8f0;
      h2 { margin: 0 0 8px; font-size: 1.25rem; }
      .subtitle { margin: 0 0 20px; color: #64748b; font-size: 0.9rem; }
      .input-group {
        display: flex; gap: 8px; margin-bottom: 24px;
        input { flex: 1; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 8px; }
        .track-btn { background: #0b2545; color: white; border: none; padding: 0 16px; border-radius: 8px; font-weight: 600; }
      }
      .status-steps {
        display: flex; flex-direction: column; gap: 12px;
        .step {
          padding: 12px; border-radius: 8px; background: #f1f5f9; font-size: 0.9rem; color: #64748b;
          &.completed { background: #dcfce7; color: #15803d; font-weight: 600; }
          &.active { background: #e0f2fe; color: #0369a1; font-weight: 700; border-left: 4px solid #0284c7; }
        }
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class StatusComponent {}
