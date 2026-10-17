import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { DIALOG_DATA, DialogRef } from '@angular/cdk/dialog';
import { MatchProposal, RdTranslatePipe, StoredRequest } from '@rd/shared';

export interface DroppedTeamRow {
  name: string;
  distanceKm: number;
  reasonKey: string;
}

export interface WhyThisTeamData {
  request: StoredRequest;
  proposals: MatchProposal[];
  droppedTeams: DroppedTeamRow[];
  onApprove?: () => void;
  onChooseAnother?: () => void;
}

@Component({
  selector: 'app-why-this-team-dialog',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="why-dialog" role="dialog" aria-modal="true" data-testid="why-team-popup" [attr.aria-label]="'why.title' | rdTranslate">
      <header class="dialog-header">
        <div>
          <h2>{{ 'why.title' | rdTranslate }}</h2>
          <p class="case-sub">{{ 'flow.forCase' | rdTranslate:{ id: data.request.id, title: data.request.place_text || '' } }}</p>
        </div>
        <button type="button" class="close-btn" (click)="close()" [attr.aria-label]="'ux.close' | rdTranslate">✕</button>
      </header>

      <div class="dialog-body">
        <div class="table-wrap">
          <table data-testid="why-team-table" class="why-table">
            <thead>
              <tr>
                <th>#</th>
                <th>{{ 'why.team' | rdTranslate }}</th>
                <th>{{ 'why.eta' | rdTranslate }}</th>
                <th>{{ 'why.seats' | rdTranslate }}</th>
                <th>{{ 'why.dist' | rdTranslate }}</th>
                <th>{{ 'why.dist30' | rdTranslate }}</th>
                <th>{{ 'why.cap25' | rdTranslate }}</th>
                <th>{{ 'why.urg25' | rdTranslate }}</th>
                <th>{{ 'why.vuln20' | rdTranslate }}</th>
                <th>{{ 'why.total' | rdTranslate }}</th>
              </tr>
            </thead>
            <tbody>
              @for (prop of data.proposals; track prop.match_id || prop.resource_id; let idx = $index) {
                <tr [class.chosen]="idx === 0">
                  <td class="num">{{ idx + 1 }}</td>
                  <td class="team-name">
                    <strong>{{ prop.resource_name }}</strong>
                    @if (idx === 0) {
                      <span class="chosen-badge">· {{ 'why.chosen' | rdTranslate }}</span>
                    }
                  </td>
                  <td class="eta">~{{ prop.eta_minutes ?? 0 }} min</td>
                  <td class="seats">{{ prop.capacity_remaining }}/{{ prop.capacity_total }} ✓</td>
                  <td class="dist">{{ prop.breakdown.distance_km }} km</td>
                  <td>{{ prop.breakdown.distance_score }}</td>
                  <td>{{ prop.breakdown.capacity_fit_score }}</td>
                  <td>{{ prop.breakdown.urgency_score }}</td>
                  <td>{{ prop.breakdown.vulnerability_fit_score }}</td>
                  <td class="score"><strong>{{ prop.score }}</strong></td>
                </tr>
              }

              @for (dropped of data.droppedTeams; track dropped.name) {
                <tr class="dropped-row">
                  <td class="num">—</td>
                  <td class="team-name muted">{{ dropped.name }}</td>
                  <td colspan="8" class="dropped-reason">
                    {{ dropped.distanceKm }} km · {{ dropped.reasonKey | rdTranslate }}
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>

        <div class="ranking-rules">
          <p class="order-rule"><strong>{{ 'why.order' | rdTranslate }}</strong></p>
          <ul class="rule-bullets">
            <li>• {{ 'why.rule1' | rdTranslate }}</li>
            <li>• {{ 'why.rule2' | rdTranslate }}</li>
            <li>• {{ 'why.rule3' | rdTranslate }}</li>
          </ul>
        </div>
      </div>

      <footer class="dialog-footer">
        <button type="button" class="btn-sec" (click)="chooseAnother()">
          {{ 'coord.chooseTeam' | rdTranslate }}
        </button>
        <button type="button" class="btn-primary" (click)="approve()">
          ✓ {{ 'coord.approve' | rdTranslate }}
        </button>
      </footer>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .why-dialog {
      background: var(--surface, #13221b);
      color: var(--text, #e8f0ec);
      border: 1px solid var(--border, #2a4136);
      border-radius: 12px;
      padding: 24px;
      width: min(860px, 94vw);
      max-height: 85vh;
      display: flex;
      flex-direction: column;
      box-shadow: 0 16px 40px rgba(0,0,0,0.5);
      font-family: var(--rd-font-family);
    }
    .dialog-header {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border, #2a4136);
    }
    .dialog-header h2 { margin: 0; font-size: 18px; font-weight: 600; color: var(--text, #fff); }
    .case-sub { margin: 4px 0 0; font-size: 12px; color: var(--muted, #728c7f); }
    .close-btn {
      background: transparent;
      border: 0;
      color: var(--text-2, #9bb0a5);
      font-size: 18px;
      cursor: pointer;
      padding: 4px 8px;
      border-radius: 6px;
    }
    .close-btn:hover { color: var(--text, #fff); background: var(--surface-2, #1b3026); }
    .dialog-body {
      flex: 1;
      overflow-y: auto;
      padding: 16px 0;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .table-wrap { overflow-x: auto; }
    .why-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      text-align: left;
    }
    .why-table th {
      padding: 8px 10px;
      font-size: 11px;
      font-weight: 600;
      color: var(--muted, #728c7f);
      border-bottom: 1px solid var(--border, #2a4136);
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .why-table td {
      padding: 10px 10px;
      border-bottom: 1px solid color-mix(in srgb, var(--border, #2a4136) 50%, transparent);
      color: var(--text, #e8f0ec);
    }
    .why-table tr.chosen td {
      background: color-mix(in srgb, var(--brand, #10b981) 12%, transparent);
    }
    .why-table tr.chosen .team-name strong {
      color: var(--brand, #34d399);
    }
    .chosen-badge {
      color: var(--brand, #34d399);
      font-weight: 600;
      font-size: 12px;
      margin-left: 6px;
    }
    .why-table .num { color: var(--muted, #728c7f); width: 24px; }
    .why-table .score { color: var(--brand, #34d399); font-size: 14px; }
    .dropped-row td { color: var(--muted, #728c7f); font-size: 12px; }
    .dropped-reason { color: var(--muted, #728c7f); font-style: italic; }
    .ranking-rules {
      background: var(--surface-2, #182a21);
      border: 1px solid var(--border, #2a4136);
      border-radius: 8px;
      padding: 14px 16px;
      font-size: 12px;
      color: var(--text-2, #9bb0a5);
    }
    .order-rule { margin: 0 0 6px; color: var(--text, #fff); }
    .rule-bullets { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
    .dialog-footer {
      display: flex;
      justify-content: flex-end;
      align-items: center;
      gap: 12px;
      padding-top: 16px;
      border-top: 1px solid var(--border, #2a4136);
    }
    .btn-sec {
      background: var(--surface-2, #1b3026);
      border: 1px solid var(--border, #2a4136);
      color: var(--text, #e8f0ec);
      padding: 10px 18px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
    }
    .btn-sec:hover { background: color-mix(in srgb, var(--surface-2, #1b3026) 80%, white); }
    .btn-primary {
      background: var(--brand, #10b981);
      border: 0;
      color: var(--on-brand, #052e16);
      padding: 10px 22px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 700;
      cursor: pointer;
    }
    .btn-primary:hover { opacity: 0.92; }
  `],
})
export class WhyThisTeamDialogComponent {
  readonly data: WhyThisTeamData = inject(DIALOG_DATA);
  private readonly dialogRef = inject(DialogRef);

  close(): void {
    this.dialogRef.close();
  }

  approve(): void {
    this.close();
    if (this.data.onApprove) {
      this.data.onApprove();
    }
  }

  chooseAnother(): void {
    this.close();
    if (this.data.onChooseAnother) {
      this.data.onChooseAnother();
    }
  }
}
