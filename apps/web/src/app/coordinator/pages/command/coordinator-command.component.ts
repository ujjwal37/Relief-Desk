import { ChangeDetectionStrategy, Component } from '@angular/core';

@Component({
  selector: 'app-coordinator-command',
  standalone: true,
  template: `
    <div class="command-container">
      <!-- 3-Pane Command View per docs/design/coordinator-command.png -->
      <section class="left-pane-queue">
        <div class="pane-header">
          <h3>Ranked Queue</h3>
          <span class="count-badge">40 Requests</span>
        </div>
        <div class="queue-item critical">
          <div class="queue-meta">
            <span class="urgency-badge">CRITICAL</span>
            <span class="score">Score: 98</span>
          </div>
          <h4>Ward 3 — Ram Ghat</h4>
          <p class="summary">8 people stranded on terrace, water rising, 3 children + 2 elderly</p>
        </div>
        <div class="queue-item high">
          <div class="queue-meta">
            <span class="urgency-badge">HIGH</span>
            <span class="score">Score: 84</span>
          </div>
          <h4>Ward 1 — Sangam Vihar</h4>
          <p class="summary">Diabetic emergency, insulin needed, road submerged chest deep</p>
        </div>
      </section>

      <section class="centre-pane-map">
        <div class="map-view-box">
          <div class="map-status">
            <span>🗺️ Map Provider: Riverbend Bounding Box</span>
            <span>Wards: 12 | Seeded Incidents: 40</span>
          </div>
        </div>
      </section>

      <section class="right-pane-decision">
        <div class="pane-header">
          <h3>Why This Match</h3>
        </div>
        <div class="decision-card">
          <h4>Proposal: Motorized Rescue Boat #02</h4>
          <div class="scores-breakdown">
            <div class="score-row"><span>Distance:</span><strong>0.8 km (Score: 30/30)</strong></div>
            <div class="score-row"><span>Capacity Fit:</span><strong>8/10 pax (Score: 25/25)</strong></div>
            <div class="score-row"><span>Vulnerability:</span><strong>Child + Elderly (Score: 35/35)</strong></div>
          </div>
          <div class="actions">
            <button class="approve-btn">Approve Dispatch</button>
            <button class="reject-btn">Reject</button>
          </div>
        </div>
      </section>
    </div>
  `,
  styles: [`
    .command-container {
      display: grid;
      grid-template-columns: 380px 1fr 360px;
      height: calc(100vh - 56px);
      background: #0b1329;
      color: #cbd5e1;
      .pane-header {
        display: flex; justify-content: space-between; align-items: center;
        padding: 12px 16px; border-bottom: 1px solid #1e293b;
        h3 { margin: 0; font-size: 1rem; color: white; }
        .count-badge { background: #1e293b; color: #14b8a6; padding: 2px 8px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; }
      }
      .left-pane-queue {
        border-right: 1px solid #1e293b; overflow-y: auto; background: #0e1726;
        .queue-item {
          padding: 14px 16px; border-bottom: 1px solid #1e293b; cursor: pointer;
          &:hover { background: #1e293b; }
          .queue-meta {
            display: flex; justify-content: space-between; margin-bottom: 6px;
            .urgency-badge { font-size: 0.7rem; font-weight: 800; padding: 2px 6px; border-radius: 4px; }
            .score { font-size: 0.75rem; color: #94a3b8; font-weight: 600; }
          }
          &.critical .urgency-badge { background: #ef4444; color: white; }
          &.high .urgency-badge { background: #f59e0b; color: white; }
          h4 { margin: 0 0 4px; font-size: 0.95rem; color: white; }
          .summary { margin: 0; font-size: 0.8rem; color: #94a3b8; }
        }
      }
      .centre-pane-map {
        background: #080f1d; display: flex; flex-direction: column;
        .map-view-box { flex: 1; display: flex; justify-content: center; align-items: center; }
        .map-status { background: #1e293b; padding: 8px 16px; border-radius: 8px; display: flex; gap: 20px; font-size: 0.85rem; }
      }
      .right-pane-decision {
        border-left: 1px solid #1e293b; background: #0e1726; padding: 0;
        .decision-card {
          padding: 16px;
          h4 { margin: 0 0 12px; color: #14b8a6; font-size: 1rem; }
          .scores-breakdown {
            display: flex; flex-direction: column; gap: 8px; margin-bottom: 20px; font-size: 0.85rem;
            .score-row { display: flex; justify-content: space-between; }
          }
          .actions {
            display: flex; gap: 10px;
            .approve-btn { flex: 1; background: #14b8a6; color: #042f2e; border: none; padding: 10px; border-radius: 8px; font-weight: 700; cursor: pointer; }
            .reject-btn { background: #334155; color: white; border: none; padding: 10px 16px; border-radius: 8px; cursor: pointer; }
          }
        }
      }
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CoordinatorCommandComponent {}
