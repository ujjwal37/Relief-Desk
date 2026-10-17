import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DIALOG_DATA, DialogRef } from '@angular/cdk/dialog';
import { peopleText } from '../../core/people-text';
import { LanguageService, RdTranslatePipe, StoredRequest } from '@rd/shared';
import { STEP_COUNT, caseRef, urgencyNumber } from '../case-facts';

export interface StepDetailData {
  request: StoredRequest;
  stepIndex: number;
  totalSteps: number;
  stepNameKey: string;
  badge: 'rules' | 'gemini' | 'cache' | 'tool' | 'test' | 'fallback' | 'you';
  providerLabel?: string;
  inputSummary?: string;
  prompt?: string;
  tools?: string[];
  rawOutput?: string;
  model?: string;
  latencyMs?: number;
  fallbackReason?: string;
  recordedAt?: string;
  /** Measured kilometres for this case and team, when the step text left a blank. */
  distanceKm?: number | null;
  onNavigate?: (newIndex: number) => void;
}

@Component({
  selector: 'app-step-detail-dialog',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="step-dialog" data-testid="step-details" [attr.aria-label]="data.stepNameKey | rdTranslate">
      <header class="dialog-header">
        <div class="h-left">
          <div class="title-wrap">
            <h2>{{ data.stepNameKey | rdTranslate }} · {{ 'step.ofN' | rdTranslate:{ k: data.stepIndex + 1, n: stepCount } }}</h2>
            <p class="case-sub">{{ 'flow.forCase' | rdTranslate:{ id: ref, title: data.request.place_text || '' } }}</p>
          </div>
        </div>
        <button type="button" class="close-btn" (click)="close()" [attr.aria-label]="'ux.close' | rdTranslate">✕</button>
      </header>

      <div class="dialog-body">
        <p class="headline">{{ headline() }}</p>
        @if (chips().length) {
          <p class="why"><span>{{ 'step.inputs' | rdTranslate }}</span></p>
          <ul class="chips">
            @for (chip of chips(); track chip) {
              <li>{{ chip }}</li>
            }
          </ul>
        }
        @if (whyLine() !== headline()) {
          <p class="why"><span>{{ 'step.why' | rdTranslate }}</span> {{ whyLine() }}</p>
        }

        @if (modelRan() || data.prompt) {
        <button type="button" class="prompt-toggle" data-testid="show-prompt" (click)="showPrompt.set(!showPrompt())" [attr.aria-expanded]="showPrompt()">
          {{ (showPrompt() ? 'step.hidePrompt' : 'step.showPrompt') | rdTranslate }}
        </button>
        @if (showPrompt()) {
          <div class="prompt-block" data-testid="prompt-and-response">
            @if (promptText()) {
              <p class="lbl">{{ 'flow.prompt' | rdTranslate }}</p>
              <pre>{{ promptText() }}</pre>
            }
            <p class="lbl">{{ 'ux.tools' | rdTranslate }}</p>
            @if (data.tools?.length) {
              <p class="tools" data-testid="step-tools">
                @for (tool of data.tools; track tool) { <code>{{ tool }}</code> }
              </p>
            } @else {
              <p class="tools" data-testid="step-tools">{{ 'ux.noTools' | rdTranslate }}</p>
            }
            <p class="lbl">{{ 'ux.raw' | rdTranslate }}</p>
            <pre>{{ rawText() }}</pre>
          </div>
        }
        }
      </div>

      <footer class="dialog-footer">
        <button type="button" class="nav-step prev" [disabled]="data.stepIndex <= 0" (click)="prevStep()">
          ‹ {{ 'step.prev' | rdTranslate }}
        </button>
        <span class="note">{{ footer() }}</span>
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
      font-size: 13px;
      font-weight: 700;
    }
    .title-wrap h2 { margin: 0; font-size: 16px; font-weight: 600; }
    .case-sub { margin: 4px 0 0; font-size: 12px; color: var(--muted, #728c7f); }
    .close-btn {
      background: transparent; border: 0; color: var(--text-2, #9bb0a5);
      font-size: 18px; cursor: pointer; padding: 4px 8px; border-radius: 6px;
    }
    .dialog-body { flex: 1; overflow-y: auto; padding: 18px 0; display: flex; flex-direction: column; gap: 12px; }
    .headline { margin: 0; font-size: 16px; line-height: 1.45; font-weight: 600; }
    .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 0; padding: 0; list-style: none; }
    .chips li {
      font-size: 12px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
      background: var(--surface-2, #1b3026); border: 1px solid var(--border, #2a4136); color: var(--text, #e8f0ec);
    }
    .why { margin: 0; font-size: 13px; line-height: 1.45; color: var(--text-2, #c5d5cc); }
    .why span { color: var(--muted, #728c7f); font-weight: 600; margin-right: 6px; }
    .tools code {
      display: inline-block; margin-right: 6px; font-size: 12px; padding: 2px 6px; border-radius: 4px;
      background: var(--surface-2, #182a21); border: 1px solid var(--border, #2a4136); color: var(--brand, #34d399);
    }
    .prompt-toggle {
      align-self: flex-start; background: transparent; border: 0; padding: 0;
      color: var(--brand, #34d399); font-weight: 600; cursor: pointer; font-size: 13px;
    }
    .prompt-block pre {
      white-space: pre-wrap; word-break: break-word; margin: 4px 0 10px;
      background: var(--surface-2, #182a21); border: 1px solid var(--border, #2a4136);
      border-radius: 8px; padding: 10px 12px; font-size: 12px; line-height: 1.45;
      max-height: 180px; overflow: auto;
    }
    .lbl { margin: 0; font-size: 11px; color: var(--muted, #728c7f); font-weight: 600; }
    .dialog-footer {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      padding-top: 16px; border-top: 1px solid var(--border, #2a4136); font-size: 12px;
    }
    .note { color: var(--text-2, #c5d5cc); text-align: center; font-weight: 600; }
    .nav-step {
      background: var(--surface-2, #1b3026); border: 1px solid var(--border, #2a4136);
      color: var(--text, #e8f0ec); padding: 6px 14px; border-radius: 6px; cursor: pointer; font-weight: 500;
    }
    .nav-step:disabled { opacity: 0.4; cursor: not-allowed; }
  `],
})
export class StepDetailDialogComponent {
  readonly data: StepDetailData = inject(DIALOG_DATA);
  private readonly dialogRef = inject(DialogRef);
  private readonly lang = inject(LanguageService);
  readonly showPrompt = signal(false);

  close(): void {
    this.dialogRef.close();
  }

  readonly stepCount = STEP_COUNT;
  get ref(): string { return caseRef(this.data.request); }

  modelRan(): boolean {
    return !!this.data.model || this.data.badge === 'gemini' || this.data.badge === 'cache' || this.data.badge === 'test';
  }

  promptText(): string {
    this.lang.currentLang();
    if (this.data.prompt) return this.data.prompt;
    if (this.data.badge === 'you' || this.modelRan() || this.isMaps()) return '';
    return this.lang.translate('step.noModel');
  }

  rawText(): string {
    return this.withKm(this.data.rawOutput || '');
  }

  headline(): string {
    this.lang.currentLang();
    const req = this.data.request;
    const t = (key: string) => this.lang.translate(key);
    const people = peopleText(req.people_count, t);
    const place = req.place_text || t('field.place');
    const kind = req.type ? t(`incidentType.${req.type}`) : t('incidentType.rescue');
    if (this.data.stepIndex === 0) {
      return t('step.headlineIntake').replace('{type}', kind).replace('{people}', people).replace('{place}', place);
    }
    if (this.data.stepIndex === 1) {
      const extra = (req.merged_count || 1) > 1
        ? t('step.headlineJoined').replace('{n}', String((req.merged_count || 1) - 1))
        : t('step.result.noDup');
      return extra;
    }
    if (this.data.stepIndex === 2) {
      return t('step.headlineUrgency').replace('{score}', String(urgencyNumber(req))).replace('{reason}', req.urgency_reason || '');
    }
    if (this.data.badge === 'you' || this.data.stepIndex === 5) {
      return t('coord.youDecide');
    }
    if (this.isMaps()) {
      const parsed = this.parse(this.data.rawOutput);
      const team = String(parsed['team'] || '');
      const km = this.kmOf(parsed);
      if (team && km != null && !/boat free/i.test(team)) {
        return t('step.headlineMatch').replace('{team}', team).replace('{km}', String(km));
      }
      if (team && !/boat free/i.test(team)) return t('step.matchNoKm').replace('{team}', team);
      const filled = this.withKm(this.plain(this.data.rawOutput));
      return filled || t('step.noTeam');
    }
    const text = this.withKm(this.plain(this.data.rawOutput));
    return text || t('flow.sentExplain');
  }

  chips(): string[] {
    this.lang.currentLang();
    const req = this.data.request;
    const t = (key: string) => this.lang.translate(key);
    const out: string[] = [];
    if (req.type) out.push(t(`incidentType.${req.type}`));
    if (req.people_count) out.push(peopleText(req.people_count, t));
    if (req.place_text) out.push(req.place_text);
    if (req.hazard && req.hazard !== 'unknown' && req.hazard !== 'none') {
      const hazard = this.lang.translate(`hazardKind.${req.hazard}`);
      out.push(hazard.startsWith('hazardKind.') ? String(req.hazard).replace(/_/g, ' ') : hazard);
    }
    const flags = req.vulnerable;
    if (flags?.child) out.push(t('coord.metaChildren'));
    if (flags?.elderly) out.push(t('coord.metaElderly'));
    if (flags?.pregnant) out.push(t('coord.metaPregnant'));
    if (flags?.medical_need) out.push(t('coord.metaMedical'));
    if (req.hoax_reason) out.push(t('chip.likelyHoax').replace('{reason}', req.hoax_reason));
    return out.slice(0, 6);
  }

  whyLine(): string {
    this.lang.currentLang();
    if (this.data.badge === 'you' || this.data.stepIndex === 5) {
      return this.lang.translate('coord.youDecide');
    }
    // Each step gives its own reason, from the same case data the card shows.
    const req = this.data.request;
    const t = (key: string) => this.lang.translate(key);
    if (this.data.stepIndex === 0) return this.headline();
    if (this.data.stepIndex === 1) {
      if ((req.merged_count || 1) <= 1) return t('step.whyDistinct');
      const key = (req.place_text || '').trim() ? 'step.whyJoined' : 'step.whyJoinedNoPlace';
      return t(key).replace('{n}', String(req.merged_count));
    }
    if (this.data.stepIndex === 2 && req.urgency_reason) return req.urgency_reason;
    if (this.isMaps()) {
      const parsed = this.parse(this.data.rawOutput);
      const km = this.kmOf(parsed);
      const team = String(parsed['team'] || '');
      if (team && km != null && !/boat free/i.test(team)) {
        return this.lang.translate('step.whyMatch').replace('{team}', team).replace('{km}', String(km));
      }
    }
    const text = this.withKm(this.plain(this.data.rawOutput));
    if (text) return text.split(/(?<=[.!?])\s/)[0] || text;
    if (this.data.stepIndex === 2 && this.data.request.urgency_reason) return this.data.request.urgency_reason;
    return this.lang.translate('coord.youDecide');
  }

  footer(): string {
    this.lang.currentLang();
    if (this.data.badge === 'you') return this.lang.translate('flow.badgeYou');
    if (this.isMaps()) return this.lang.translate(this.data.providerLabel === 'Google Maps' ? 'flow.badgeTool' : 'flow.badgeStraight');
    if (this.data.badge === 'test') return this.lang.translate('badge.testModel');
    if (this.data.badge === 'gemini' && this.data.model) {
      const sec = this.data.latencyMs ? ` · ${(this.data.latencyMs / 1000).toFixed(1)} s` : '';
      return `Gemini ${this.data.model}${sec}`;
    }
    if (this.data.badge === 'gemini') return this.lang.translate('badge.gemini');
    if (this.data.badge === 'cache') {
      const date = this.data.recordedAt ? ` · ${this.data.recordedAt}` : '';
      return `${this.lang.translate('badge.recorded')}${date}`;
    }
    return this.lang.translate('coord.aiOffline');
  }

  prevStep(): void {
    if (this.data.stepIndex > 0 && this.data.onNavigate) this.data.onNavigate(this.data.stepIndex - 1);
  }

  nextStep(): void {
    if (this.data.stepIndex < this.data.totalSteps - 1 && this.data.onNavigate) this.data.onNavigate(this.data.stepIndex + 1);
  }

  isMaps(): boolean {
    return this.data.badge === 'tool' || this.data.providerLabel === 'Google Maps' || this.data.providerLabel === 'rules' || this.data.stepIndex === 3;
  }

  private parse(output?: string): Record<string, unknown> {
    if (!output) return {};
    try {
      const json = JSON.parse(output);
      return json && typeof json === 'object' ? json as Record<string, unknown> : {};
    } catch {
      return {};
    }
  }

  private plain(output?: string): string {
    const text = (output || '').trim();
    if (!text || text.startsWith('{') || text.startsWith('[')) return '';
    return text;
  }

  private kmOf(parsed: Record<string, unknown>): number | null {
    const raw = parsed['km'] ?? parsed['distance_km'];
    const n = typeof raw === 'number' ? raw : Number(raw);
    if (raw != null && raw !== '' && Number.isFinite(n)) return n;
    return this.data.distanceKm != null && Number.isFinite(this.data.distanceKm) ? this.data.distanceKm : null;
  }

  /** A blank "— km" is filled from the measured distance. It is never left as a dash. */
  private withKm(text: string): string {
    return this.oneScore(this.withKmRaw(text));
  }

  /** The urgency step shows the case's current score (re-scored after merges), the same number as the card. */
  private oneScore(text: string): string {
    if (this.data.stepIndex !== 2 || !text) return text;
    const now = Math.round(this.data.request?.urgency_score || 0);
    return text.replace(/((?:score|urgency)["']?\s*[:=]?\s*)(\d+(?:\.\d+)?)/gi, (_m, pre) => `${pre}${now}`);
  }

  private withKmRaw(text: string): string {
    const km = this.data.distanceKm;
    if (!text || !text.includes('—')) return text;
    if (km == null || !Number.isFinite(km)) return text.replace(/\s*:?\s*—\s*km/g, '').trim();
    return text.replace(/—\s*km/g, `${Number(km).toFixed(1)} km`);
  }
}
