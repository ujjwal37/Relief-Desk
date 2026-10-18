import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  HostListener,
  computed,
  effect,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';
import { CoordUiService } from '../services/coord-ui.service';

/** Exactly 5 steps pointing at live elements on the Command screen. */
export interface StepDef {
  target: string;
  title: string;
  body: string;
}

export const TOUR_STEPS: StepDef[] = [
  { target: '[data-testid="life-threat-card"]', title: 'tour.s1t', body: 'tour.s1b' },
  { target: 'app-ai-stepper, .steps-line', title: 'tour.s2t', body: 'tour.s2b' },
  { target: '[data-tour="actions"], .best-team-banner', title: 'tour.s3t', body: 'tour.s3b' },
  { target: '[data-tour="dup"], [data-testid="dup-review"]', title: 'tour.s4t', body: 'tour.s4b' },
  { target: '[data-testid="try-citizen"], [data-tour="reporter"]', title: 'tour.s5t', body: 'tour.s5b' },
];

export function tourAnchor(selector: string): HTMLElement | null {
  const selectors = selector.split(',').map((s) => s.trim());
  for (const sel of selectors) {
    const el = document.querySelector(sel) as HTMLElement | null;
    if (el) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) return el;
    }
  }
  return null;
}

/** Non-blocking 5-step tour with corner prompt. No backdrop, no scrim, no focus trap. */
@Component({
  selector: 'app-tour',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (ui.cornerPromptOpen()) {
      <div class="tour-corner-card" [class.with-panel]="ui.phonePanelOpen()" data-testid="tour-corner-card" role="region" [attr.aria-label]="'tour.prompt' | rdTranslate">
        <div class="tcc-head">
          <span class="tcc-sparkle" aria-hidden="true">✨</span>
          <strong class="tcc-title">{{ 'tour.prompt' | rdTranslate }}</strong>
        </div>
        <div class="tcc-actions">
          <button type="button" class="tcc-start" data-testid="tour-start" (click)="ui.startTour()">
            {{ 'tour.start' | rdTranslate }}
          </button>
          <span class="tcc-sep" aria-hidden="true">·</span>
          <button type="button" class="tcc-skip" data-testid="tour-skip" (click)="ui.dismissCornerPrompt()">
            {{ 'tour.skip' | rdTranslate }}
          </button>
        </div>
      </div>
    }

    @if (ui.tourOpen() && current(); as step) {
      @if (rect(); as r) {
        <div
          class="tour-outline"
          data-testid="tour-outline"
          [style.top.px]="r.top"
          [style.left.px]="r.left"
          [style.width.px]="r.width"
          [style.height.px]="r.height"
        ></div>
      }
      <div
        class="tour-callout"
        role="region"
        data-testid="tour"
        [attr.aria-label]="step.title | rdTranslate"
        #card
        tabindex="-1"
        [style.top.px]="cardPos().top"
        [style.left.px]="cardPos().left"
      >
        <div class="tc-head">
          <p class="tc-step" data-testid="tour-step">{{ stepLabel() }}</p>
          <button
            type="button"
            class="tc-close"
            data-testid="tour-close"
            (click)="skip()"
            [attr.aria-label]="'tour.skip' | rdTranslate"
          >
            ✕
          </button>
        </div>
        <h3 class="tc-title">{{ step.title | rdTranslate }}</h3>
        <p class="tc-body">{{ step.body | rdTranslate }}</p>
        <div class="tc-foot">
          <button type="button" class="tc-skip-btn" data-testid="tour-skip" (click)="skip()">
            {{ 'tour.skip' | rdTranslate }}
          </button>
          <span class="tc-dots" aria-hidden="true">
            @for (s of liveSteps(); track $index) {
              <i [class.on]="$index === index()"></i>
            }
          </span>
          @if (index() > 0) {
            <button type="button" class="tc-back-btn" (click)="go(-1)">
              {{ 'tour.back' | rdTranslate }}
            </button>
          }
          <button type="button" class="tc-next-btn" data-testid="tour-next" (click)="next()">
            {{ (last() ? 'tour.done' : 'tour.next') | rdTranslate }}
          </button>
        </div>
      </div>
    }
  `,
  styles: [
    `
      .tour-corner-card {
        position: fixed;
        bottom: 24px;
        right: 24px;
        z-index: 1050;
        background: var(--surface);
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: var(--r2, 12px);
        box-shadow: var(--e3, 0 10px 25px rgba(0, 0, 0, 0.15));
        padding: 12px 16px;
        display: flex;
        align-items: center;
        gap: 12px;
        font-family: var(--rd-font-family);
      }
      .tour-corner-card.with-panel {
        right: calc(390px + 24px);
      }
      .tcc-head {
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .tcc-sparkle {
        font-size: 14px;
      }
      .tcc-title {
        font-size: 13px;
        font-weight: 600;
      }
      .tcc-actions {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .tcc-start {
        background: var(--brand);
        color: var(--on-brand, #fff);
        border: 0;
        border-radius: 6px;
        font-size: 12px;
        font-weight: 600;
        padding: 6px 12px;
        cursor: pointer;
      }
      .tcc-sep {
        color: var(--text-2, #888);
      }
      .tcc-skip {
        background: transparent;
        color: var(--text-2, #888);
        border: 0;
        font-size: 12px;
        font-weight: 600;
        padding: 6px 4px;
        cursor: pointer;
      }
      .tcc-skip:hover {
        color: var(--text);
      }

      .tour-outline {
        position: fixed;
        z-index: 1040;
        border-radius: 8px;
        border: 2px solid var(--brand);
        box-shadow: 0 0 0 3px color-mix(in srgb, var(--brand) 25%, transparent);
        pointer-events: none;
        transition: all 180ms ease;
      }

      .tour-callout {
        position: fixed;
        z-index: 1041;
        width: 320px;
        max-width: calc(100vw - 24px);
        background: var(--surface);
        color: var(--text);
        border: 1px solid var(--border);
        border-radius: var(--r2, 12px);
        box-shadow: var(--e3, 0 10px 25px rgba(0, 0, 0, 0.15));
        padding: 16px;
        outline: none;
        font-family: var(--rd-font-family);
        pointer-events: auto;
      }
      .tc-head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 6px;
      }
      .tc-step {
        margin: 0;
        font-size: 12px;
        color: var(--text-2, #888);
        font-weight: 600;
      }
      .tc-close {
        background: transparent;
        border: 0;
        color: var(--text-2, #888);
        cursor: pointer;
        padding: 2px 6px;
        font-size: 14px;
        border-radius: 4px;
      }
      .tc-close:hover {
        color: var(--text);
      }
      .tc-title {
        margin: 0 0 6px;
        font-size: 15px;
        line-height: 1.3;
        font-weight: 700;
      }
      .tc-body {
        margin: 0 0 14px;
        font-size: 13px;
        line-height: 1.45;
        color: var(--text-2, #555);
      }
      .tc-foot {
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .tc-dots {
        display: inline-flex;
        gap: 4px;
        flex: 1;
        justify-content: center;
      }
      .tc-dots i {
        width: 6px;
        height: 6px;
        border-radius: 50%;
        background: var(--border, #ddd);
      }
      .tc-dots i.on {
        background: var(--brand);
      }
      .tc-skip-btn,
      .tc-back-btn {
        background: transparent;
        border: 0;
        color: var(--text-2, #888);
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        padding: 6px 10px;
        border-radius: 6px;
      }
      .tc-skip-btn:hover,
      .tc-back-btn:hover {
        color: var(--text);
      }
      .tc-next-btn {
        background: var(--brand);
        color: var(--on-brand, #fff);
        border: 0;
        border-radius: 6px;
        font-size: 13px;
        font-weight: 600;
        cursor: pointer;
        padding: 6px 14px;
      }

      @media (max-width: 600px) {
        .tour-corner-card {
          left: 12px;
          right: 12px;
          bottom: 12px;
        }
      }
    `,
  ],
})
export class TourComponent {
  readonly ui = inject(CoordUiService);
  private lang = inject(LanguageService);
  private card = viewChild<ElementRef<HTMLElement>>('card');

  /** Steps whose anchor elements are present on screen. */
  readonly liveSteps = signal<StepDef[]>([]);
  readonly index = computed(() => {
    const total = this.liveSteps().length;
    if (total === 0) return 0;
    return Math.min(this.ui.tourStep(), total - 1);
  });
  readonly current = computed(() => this.liveSteps()[this.index()] || null);
  readonly rect = signal<{ top: number; left: number; width: number; height: number } | null>(null);
  readonly cardPos = signal({ top: 80, left: 80 });

  constructor() {
    effect(() => {
      if (!this.ui.tourOpen()) {
        this.liveSteps.set([]);
        this.rect.set(null);
        return;
      }
      this.ui.tourStep();
      setTimeout(() => {
        this.refreshLiveSteps();
        this.place(true);
      }, 50);
    });
  }

  private refreshLiveSteps(): void {
    const live = TOUR_STEPS.filter((s) => !!tourAnchor(s.target));
    if (!live.length) {
      this.ui.finishTour();
      return;
    }
    this.liveSteps.set(live);
  }

  last = () => this.index() >= this.liveSteps().length - 1;

  stepLabel(): string {
    this.lang.currentLang();
    return this.lang
      .translate('tour.step')
      .replace('{a}', String(this.index() + 1))
      .replace('{b}', String(this.liveSteps().length));
  }

  go(delta: number): void {
    const nextIdx = this.index() + delta;
    if (nextIdx < 0) return;
    if (nextIdx >= this.liveSteps().length) {
      this.skip();
      return;
    }
    this.ui.tourStep.set(nextIdx);
    setTimeout(() => this.place(true), 30);
  }

  next(): void {
    this.last() ? this.skip() : this.go(1);
  }

  skip(): void {
    this.ui.finishTour();
  }

  @HostListener('window:resize') onResize(): void {
    this.place(false);
  }

  place(scroll: boolean): void {
    const step = this.current();
    if (!this.ui.tourOpen() || !step) return;
    let el = tourAnchor(step.target);
    if (!el) {
      // Element missing, skip to next live step if any
      this.refreshLiveSteps();
      el = this.current() ? tourAnchor(this.current()!.target) : null;
      if (!el) {
        this.ui.finishTour();
        return;
      }
    }
    if (scroll) {
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      el = tourAnchor(step.target);
    }
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const availW = this.ui.phonePanelOpen() ? Math.max(320, vw - 390) : vw;
    const cw = Math.min(320, availW - 24);
    const ch = 200;

    if (!el) {
      this.rect.set(null);
      this.cardPos.set({ top: Math.max(12, (vh - ch) / 2), left: Math.max(12, (availW - cw) / 2) });
      return;
    }

    const r = el.getBoundingClientRect();
    const pad = 4;
    const box = {
      top: Math.max(0, r.top - pad),
      left: Math.max(0, r.left - pad),
      width: r.width + pad * 2,
      height: r.height + pad * 2,
    };
    this.rect.set(box);

    let top = box.top + box.height + 8;
    if (top + ch > vh - 12) {
      top = box.top - ch - 8;
    }
    if (top < 12) {
      top = Math.max(12, Math.min(vh - ch - 12, box.top + 8));
    }
    let left = Math.max(12, Math.min(availW - cw - 12, box.left));
    this.cardPos.set({ top, left });
  }

  @HostListener('document:keydown', ['$event']) onKey(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      if (this.ui.tourOpen()) {
        e.preventDefault();
        this.skip();
        return;
      }
      if (this.ui.cornerPromptOpen()) {
        e.preventDefault();
        this.ui.dismissCornerPrompt();
        return;
      }
    }
    // Note: Tab is deliberately NOT intercepted or trapped, preserving complete non-blocking behavior.
  }
}
