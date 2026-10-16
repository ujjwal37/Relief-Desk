import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { DIALOG_DATA, DialogRef } from '@angular/cdk/dialog';
import { RdTranslatePipe, StoredRequest } from '@rd/shared';

export interface StepDetailData {
  request: StoredRequest;
  stepIndex: number;
  totalSteps: number;
  stepNameKey: string;
  badge: 'rules' | 'gemini' | 'cache' | 'tool' | 'test';
  inputSummary?: string;
  prompt?: string;
  tools?: string[];
  rawOutput?: string;
  model?: string;
  latencyMs?: number;
  fallbackReason?: string;
  onNavigate?: (newIndex: number) => void;
}

@Component({
  selector: 'app-step-detail-dialog',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="step-dialog" role="dialog" aria-modal="true" data-testid="step-details" [attr.aria-label]="data.stepNameKey | rdTranslate">
      <header class="dialog-header">
        <div class="h-left">
          <span class="step-num-badge">
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
              <path d="M5 12l5 5L20 7" />
            </svg>
          </span>
          <div class="title-wrap">
            <div class="step-title-line">
              <h2>{{ data.stepIndex + 1 }} · {{ data.stepNameKey | rdTranslate }}</h2>
              <span class="badge" [class.gemini]="data.badge === 'gemini' || data.badge === 'cache'">{{ badgeLabel() }}</span>
            </div>
            <p class="case-sub">{{ 'flow.forCase' | rdTranslate:{ id: data.request.id, title: data.request.place_text || '' } }}</p>
          </div>
        </div>
        <button type="button" class="close-btn" (click)="close()" [attr.aria-label]="'ux.close' | rdTranslate">✕</button>
      </header>

      <div class="dialog-body">
        <div class="row">
          <span class="lbl">{{ 'ux.input' | rdTranslate }}</span>
          <div class="val text-bubble">{{ data.inputSummary || data.request.raw_text }}</div>
        </div>

        <div class="row">
          <span class="lbl">{{ 'flow.prompt' | rdTranslate }}</span>
          <div class="val">{{ data.prompt || ('step.noModel' | rdTranslate) }}</div>
        </div>

        <div class="row">
          <span class="lbl">{{ 'ux.tools' | rdTranslate }}</span>
          <div class="val">
            @if (data.tools && data.tools.length) {
              <div class="tool-tags">
                @for (t of data.tools; track t) {
                  <code>{{ t }}</code>
                }
              </div>
            } @else {
              <span>—</span>
            }
          </div>
        </div>

        <div class="row">
          <span class="lbl">{{ 'ux.raw' | rdTranslate }}</span>
          <div class="val text-bubble">{{ data.rawOutput || ('ux.none' | rdTranslate) }}</div>
        </div>

        <div class="row">
          <span class="lbl">{{ 'flow.modelLatency' | rdTranslate }}</span>
          <div class="val">{{ data.model || '—' }} · {{ data.latencyMs ? data.latencyMs + ' ms' : '—' }}</div>
        </div>

        @if (data.fallbackReason) {
          <div class="row">
            <span class="lbl">{{ 'flow.fellBack' | rdTranslate }}</span>
            <div class="val text-bubble fallback-text">{{ data.fallbackReason }}</div>
          </div>
        }
      </div>

      <footer class="dialog-footer">
        <button type="button" class="nav-step prev" [disabled]="data.stepIndex <= 0" (click)="prevStep()">
          ‹ {{ 'step.prev' | rdTranslate }}
        </button>
        <span class="note">{{ 'coord.youDecide' | rdTranslate }}</span>
        <button type="button" class="nav-step next" [disabled]="data.stepIndex >= data.totalSteps - 1" (click)="nextStep()">
          {{ 'step.next' | rdTranslate }} ›
        </button>
      </footer>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .step-dialog {
      background: var(--surface, #13221b);
      color: var(--text, #e8f0ec);
      border: 1px solid var(--border, #2a4136);
      border-radius: 12px;
      padding: 24px;
      width: min(660px, 92vw);
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
      gap: 16px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--border, #2a4136);
    }
    .h-left { display: flex; gap: 12px; align-items: flex-start; }
    .step-num-badge {
      width: 28px;
      height: 28px;
      border-radius: 50%;
      background: var(--brand, #10b981);
      color: #fff;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      flex-shrink: 0;
      margin-top: 2px;
    }
    .title-wrap h2 { margin: 0; font-size: 16px; font-weight: 600; color: var(--text, #fff); }
    .step-title-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 7px;
      border-radius: 6px;
      background: var(--surface-2, #1b3026);
      color: var(--text-2, #9bb0a5);
      border: 1px solid var(--border, #2a4136);
    }
    .badge.gemini {
      background: color-mix(in srgb, var(--brand, #10b981) 18%, transparent);
      color: var(--brand, #34d399);
      border-color: var(--brand, #10b981);
    }
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
      padding: 18px 0;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .row {
      display: grid;
      grid-template-columns: 140px 1fr;
      gap: 16px;
      font-size: 13px;
      line-height: 1.5;
    }
    .lbl { color: var(--muted, #728c7f); font-weight: 500; }
    .val { color: var(--text, #e8f0ec); }
    .text-bubble {
      background: var(--surface-2, #182a21);
      border: 1px solid var(--border, #2a4136);
      border-radius: 8px;
      padding: 10px 14px;
      word-break: break-word;
    }
    .fallback-text { color: #f59e0b; }
    .tool-tags code {
      display: inline-block;
      background: var(--surface-2, #182a21);
      border: 1px solid var(--border, #2a4136);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 12px;
      color: var(--brand, #34d399);
      margin-right: 6px;
    }
    .dialog-footer {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-top: 16px;
      border-top: 1px solid var(--border, #2a4136);
      font-size: 12px;
    }
    .note { color: var(--muted, #728c7f); }
    .nav-step {
      background: var(--surface-2, #1b3026);
      border: 1px solid var(--border, #2a4136);
      color: var(--text, #e8f0ec);
      padding: 6px 14px;
      border-radius: 6px;
      cursor: pointer;
      font-weight: 500;
    }
    .nav-step:disabled { opacity: 0.4; cursor: not-allowed; }
    .nav-step:not(:disabled):hover { border-color: var(--brand, #10b981); color: var(--brand, #34d399); }
  `],
})
export class StepDetailDialogComponent {
  readonly data: StepDetailData = inject(DIALOG_DATA);
  private readonly dialogRef = inject(DialogRef);

  close(): void {
    this.dialogRef.close();
  }

  badgeLabel(): string {
    if (this.data.badge === 'gemini') return 'Gemini';
    if (this.data.badge === 'cache') return 'Recorded (Gemini)';
    if (this.data.badge === 'test') return 'Test model';
    return 'Rules';
  }

  prevStep(): void {
    if (this.data.stepIndex > 0 && this.data.onNavigate) {
      this.data.onNavigate(this.data.stepIndex - 1);
    }
  }

  nextStep(): void {
    if (this.data.stepIndex < this.data.totalSteps - 1 && this.data.onNavigate) {
      this.data.onNavigate(this.data.stepIndex + 1);
    }
  }
}
