import { ChangeDetectionStrategy, Component, computed, inject, input, output } from '@angular/core';
import { peopleText } from '../../core/people-text';
import { LanguageService, MatchProposal, RdTranslatePipe, StoredRequest } from '@rd/shared';

export interface StepStatusInfo {
  agent: 'Intake' | 'Dedupe' | 'Triage' | 'Matching' | 'Explainer';
  status: 'done' | 'working' | 'pending' | 'failed';
}

@Component({
  selector: 'app-ai-stepper',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="stepper-card">
      <header class="stepper-head">
        <div class="head-left">
          <span class="step-count-title">{{ 'flow.headline' | rdTranslate:{ n: 6 } }}</span>
          <span class="run-badge">{{ runBadge() }}</span>
        </div>
        <button type="button" class="how-decided-btn" (click)="howDecided.emit()">
          {{ 'ux.viewTrace' | rdTranslate }}
        </button>
      </header>

      <div class="stepper-nodes" role="tablist">
        <!-- Node 0: Intake -->
        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-intake"
          [class.done]="nodeStatus(0) === 'done'"
          [class.working]="nodeStatus(0) === 'working'"
          [class.failed]="nodeStatus(0) === 'failed'"
          (click)="openStepDetail.emit(0)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(0) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else if (nodeStatus(0) === 'working') {
                <i class="spin"></i>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <span class="node-title">{{ 'steps.short.intake' | rdTranslate }}</span>
          <span class="node-result">{{ intakeResult() }}</span>
          <span class="node-badge" [class.gem]="stepBadge(0).gemini">{{ stepBadge(0).text }}</span>
        </button>

        <!-- Connector line 0-1 -->
        <div class="line" [class.done]="nodeStatus(0) === 'done'"></div>

        <!-- Node 1: Dedupe -->
        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-dedupe"
          [class.done]="nodeStatus(1) === 'done'"
          [class.working]="nodeStatus(1) === 'working'"
          [class.failed]="nodeStatus(1) === 'failed'"
          (click)="openStepDetail.emit(1)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(1) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else if (nodeStatus(1) === 'working') {
                <i class="spin"></i>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <div class="node-title-wrap">
            <span class="node-title">{{ 'steps.short.dedupe' | rdTranslate }}</span>
            <span class="tag-parallel">{{ 'step.parallel' | rdTranslate }}</span>
          </div>
          <span class="node-result">{{ dedupeResult() }}</span>
          <span class="node-badge" [class.gem]="stepBadge(1).gemini">{{ stepBadge(1).text }}</span>
        </button>

        <!-- Connector line 1-2 -->
        <div class="line" [class.done]="nodeStatus(1) === 'done'"></div>

        <!-- Node 2: Triage -->
        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-triage"
          [class.done]="nodeStatus(2) === 'done'"
          [class.working]="nodeStatus(2) === 'working'"
          [class.failed]="nodeStatus(2) === 'failed'"
          (click)="openStepDetail.emit(2)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(2) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else if (nodeStatus(2) === 'working') {
                <i class="spin"></i>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <div class="node-title-wrap">
            <span class="node-title">{{ 'steps.short.urgency' | rdTranslate }}</span>
            <span class="tag-parallel">{{ 'step.parallel' | rdTranslate }}</span>
          </div>
          <span class="node-result">{{ urgencyResult() }}</span>
          <span class="node-badge" [class.gem]="stepBadge(2).gemini">{{ stepBadge(2).text }}</span>
        </button>

        <!-- Connector line 2-3 -->
        <div class="line" [class.done]="nodeStatus(2) === 'done'"></div>

        <!-- Node 3: Matching -->
        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-matching"
          [class.done]="nodeStatus(3) === 'done'"
          [class.working]="nodeStatus(3) === 'working'"
          [class.failed]="nodeStatus(3) === 'failed'"
          (click)="openStepDetail.emit(3)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(3) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else if (nodeStatus(3) === 'working') {
                <i class="spin"></i>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <span class="node-title">{{ 'steps.short.maps' | rdTranslate }}</span>
          <span class="node-result">{{ matchingResult() }}</span>
          <span class="node-badge" [class.gem]="stepBadge(3).gemini">{{ stepBadge(3).text }}</span>
        </button>

        <!-- Connector line 3-4 -->
        <div class="line" [class.done]="nodeStatus(3) === 'done'"></div>

        <!-- Node 4: Explainer -->
        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-explainer"
          [class.done]="nodeStatus(4) === 'done'"
          [class.working]="nodeStatus(4) === 'working'"
          [class.failed]="nodeStatus(4) === 'failed'"
          (click)="openStepDetail.emit(4)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(4) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else if (nodeStatus(4) === 'working') {
                <i class="spin"></i>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <span class="node-title">{{ 'steps.short.explain' | rdTranslate }}</span>
          <span class="node-result">{{ explainResult() }}</span>
          <span class="node-badge" [class.gem]="stepBadge(4).gemini">{{ stepBadge(4).text }}</span>
        </button>

        <div class="line" [class.done]="nodeStatus(4) === 'done'"></div>

        <button
          type="button"
          class="step-node"
          data-testid="stepper-node-approval"
          [class.done]="nodeStatus(4) === 'done'"
          (click)="openStepDetail.emit(5)"
        >
          <div class="node-indicator">
            <span class="indicator-icon">
              @if (nodeStatus(4) === 'done') {
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M5 12l5 5L20 7"/></svg>
              } @else {
                <span class="dot"></span>
              }
            </span>
          </div>
          <span class="node-title">{{ 'steps.short.you' | rdTranslate }}</span>
          <span class="node-result">{{ 'coord.youDecide' | rdTranslate }}</span>
        </button>
      </div>

      <p class="same-time-note">
        {{ 'step.sameTime' | rdTranslate }}
      </p>
    </div>
  `,
  styles: [`
    :host { display: block; }
    .stepper-card {
      background: var(--surface, #13221b);
      border: 1px solid var(--border, #2a4136);
      border-radius: 12px;
      padding: 16px 20px 12px;
      font-family: var(--rd-font-family);
    }
    .stepper-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 14px;
    }
    .head-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .step-count-title {
      font-size: 14px;
      font-weight: 700;
      color: var(--text, #fff);
    }
    .run-badge {
      font-size: 11px;
      font-weight: 600;
      padding: 2px 8px;
      border-radius: 6px;
      background: var(--surface-2, #1b3026);
      color: var(--text-2, #9bb0a5);
      border: 1px solid var(--border, #2a4136);
    }
    .how-decided-btn {
      background: transparent;
      border: 0;
      color: var(--brand, #34d399);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      padding: 4px 8px;
    }
    .how-decided-btn:hover { text-decoration: underline; }
    .stepper-nodes {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      position: relative;
    }
    .step-node {
      background: transparent;
      border: 0;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      flex: 1;
      min-width: 0;
      cursor: pointer;
      padding: 0 4px;
      font-family: inherit;
    }
    .node-indicator {
      margin-bottom: 8px;
      position: relative;
      z-index: 2;
    }
    .indicator-icon {
      width: 26px;
      height: 26px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: var(--surface-2, #182a21);
      border: 2px solid var(--border, #2a4136);
      color: var(--muted, #728c7f);
      transition: all 0.2s ease;
    }
    .step-node.done .indicator-icon {
      background: var(--brand, #10b981);
      border-color: var(--brand, #10b981);
      color: #fff;
    }
    .step-node.working .indicator-icon {
      border-color: var(--brand, #10b981);
      background: var(--surface-2, #182a21);
    }
    .spin {
      width: 12px;
      height: 12px;
      border: 2px solid transparent;
      border-top-color: var(--brand, #10b981);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }
    @keyframes spin { 100% { transform: rotate(360deg); } }
    .dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: var(--muted, #728c7f);
    }
    .line {
      flex: 1;
      height: 2px;
      background: var(--border, #2a4136);
      margin-top: 12px;
      margin-left: -12px;
      margin-right: -12px;
      z-index: 1;
      transition: background 0.2s ease;
    }
    .line.done {
      background: var(--brand, #10b981);
    }
    .node-title-wrap {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 4px;
      flex-wrap: wrap;
    }
    .node-title {
      font-size: 12px;
      font-weight: 600;
      color: var(--text, #e8f0ec);
      line-height: 1.25;
      white-space: normal;
      overflow-wrap: break-word;
      hyphens: auto;
    }
    .tag-parallel {
      font-size: 9px;
      font-weight: 600;
      padding: 1px 4px;
      border-radius: 4px;
      border: 1px dashed var(--border, #3d5849);
      color: var(--muted, #9bb0a5);
    }
    .node-result {
      font-size: 11px;
      color: var(--muted, #9bb0a5);
      margin-top: 3px;
      line-height: 1.25;
      max-width: 100%;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .node-badge { margin-top: 4px; font-size: 10.5px; font-weight: 600; padding: 1px 6px; border-radius: 999px; background: var(--surface-2); color: var(--text-2); font-variant-numeric: tabular-nums; }
    .node-badge.gem { color: var(--gemini, #6d28d9); background: color-mix(in srgb, var(--gemini, #6d28d9) 14%, transparent); }
    .same-time-note {
      text-align: center;
      font-size: 11px;
      color: var(--muted, #728c7f);
      margin: 10px 0 0;
    }
  `],
})
export class AiStepperComponent {
  private readonly lang = inject(LanguageService);

  /** Per-step badge from the real trace: Gemini with its measured time, Recorded, or Rules. Never invented. */
  stepBadge(i: number): { text: string; gemini: boolean } {
    this.lang.currentLang();
    const agent = ['Intake', 'Dedupe', 'Triage', 'Matching', 'Explainer'][i];
    const step = (this.request()?.trace || []).find((row) => row.agent === agent) as { provider?: string | null; cached?: boolean; latency_ms?: number } | undefined;
    if (!step) return { text: this.lang.translate('steps.badgeRules'), gemini: false };
    if (step.cached || step.provider === 'cache') return { text: this.lang.translate('steps.badgeRecorded'), gemini: false };
    if (step.provider === 'gemini') {
      const t = typeof step.latency_ms === 'number' && step.latency_ms > 0 ? ` ${(step.latency_ms / 1000).toFixed(1)}s` : '';
      return { text: '✨ Gemini' + t, gemini: true };
    }
    return { text: this.lang.translate('steps.badgeRules'), gemini: false };
  }

  readonly request = input<StoredRequest | null | undefined>(null);
  readonly activeProposal = input<MatchProposal | null | undefined>(null);
  readonly runBadge = input<string>('');
  readonly isAnalysing = input<boolean>(false);

  readonly openStepDetail = output<number>();
  readonly howDecided = output<void>();

  nodeStatus(index: number): 'done' | 'working' | 'pending' | 'failed' {
    const req = this.request();
    if (!req) return 'pending';
    const trace = req.trace || [];
    if (this.isAnalysing()) {
      if (index === 0) return trace.length > 0 ? 'done' : 'working';
      if (index <= trace.length) return 'working';
      return 'pending';
    }
    if (trace.length > index) {
      const step = trace[index];
      if (step?.status === 'error') return 'failed';
      return 'done';
    }
    return req ? 'done' : 'pending';
  }

  readonly intakeResult = computed<string>(() => {
    const req = this.request();
    if (!req) return '—';
    const t = (k: string) => this.lang.translate(k);
    const need = req.type ? t(`incidentType.${req.type}`) : t('incidentType.rescue');
    return `${need} · ${peopleText(req.people_count, t)}`;
  });

  readonly dedupeResult = computed<string>(() => {
    const req = this.request();
    if (!req) return '—';
    if ((req.merged_count || 1) > 1) {
      return `${req.merged_count} joined`;
    }
    if (req.possible_duplicate) {
      return `Maybe #${req.possible_duplicate.target_id}`;
    }
    return this.lang.translate('step.result.noDup');
  });

  readonly urgencyResult = computed<string>(() => {
    const req = this.request();
    if (!req) return '—';
    const score = Math.round(req.urgency_score);
    const band = score >= 80 ? this.lang.translate('band.critical') : this.lang.translate('band.urgent');
    return `${score} · ${band}`;
  });

  readonly matchingResult = computed<string>(() => {
    const prop = this.activeProposal();
    if (!prop) return '—';
    const kind = prop.resource_kind === 'boat' ? 'Boat' : 'Team';
    const km = prop.breakdown?.distance_km;
    if (km == null || Number.isNaN(Number(km))) return kind;
    return `${kind} · ${km} km`;
  });

  readonly explainResult = computed<string>(() => {
    const req = this.request();
    if (!req) return '—';
    return this.lang.translate('why.order');
  });
}
