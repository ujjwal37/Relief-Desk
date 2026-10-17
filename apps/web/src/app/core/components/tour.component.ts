import { ChangeDetectionStrategy, Component, ElementRef, HostListener, computed, effect, inject, signal, viewChild } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';
import { CoordUiService } from '../services/coord-ui.service';

/** Each step points at something on the current Command screen. A step whose element is not on screen is skipped. */
interface Step { target: string; title: string; body: string; }
export const TOUR_STEPS: Step[] = [
  { target: '[data-testid="life-threat-card"]', title: 'tour.s1t', body: 'tour.s1b' },
  { target: 'app-ai-stepper', title: 'tour.s2t', body: 'tour.s2b' },
  { target: '[data-tour="actions"]', title: 'tour.s3t', body: 'tour.s3b' },
  { target: '[data-tour="dup"]', title: 'tour.s4t', body: 'tour.s4b' },
  { target: '[data-tour="reporter"]', title: 'tour.s5t', body: 'tour.s5b' },
];

export function tourAnchor(selector: string): HTMLElement | null {
  const el = document.querySelector(selector) as HTMLElement | null;
  if (!el) return null;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0 ? el : null;
}

/** Short guided tour. Read-only: it never sends a report or approves anything. Skip and Esc always close it. */
@Component({
  selector: 'app-tour',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (ui.tourOpen() && current(); as step) {
      <div class="shade" (click)="skip()"></div>
      @if (rect(); as r) {
        <div class="spot" [style.top.px]="r.top" [style.left.px]="r.left" [style.width.px]="r.width" [style.height.px]="r.height"></div>
      }
      <div class="card" role="dialog" aria-modal="true" data-testid="tour" [attr.aria-label]="step.title | rdTranslate" #card tabindex="-1"
        [style.top.px]="cardPos().top" [style.left.px]="cardPos().left">
        <p class="step" data-testid="tour-step">{{ stepLabel() }}</p>
        <h2>{{ step.title | rdTranslate }}</h2>
        <p class="body">{{ step.body | rdTranslate }}</p>
        <div class="foot">
          <button type="button" class="skip" data-testid="tour-skip" (click)="skip()">{{ 'coord.dismissTour' | rdTranslate }}</button>
          <span class="dots" aria-hidden="true">@for (s of steps(); track $index) { <i [class.on]="$index === index()"></i> }</span>
          @if (index() > 0) { <button type="button" class="back" (click)="go(-1)">{{ 'tour.back' | rdTranslate }}</button> }
          <button type="button" class="next" data-testid="tour-next" (click)="next()">{{ (last() ? 'tour.done' : 'tour.next') | rdTranslate }}</button>
        </div>
      </div>
    }
  `,
  styles: [`
    .shade { position:fixed; inset:0; z-index:2000; }
    .spot { position:fixed; z-index:2001; border-radius:12px; box-shadow:0 0 0 9999px var(--scrim); outline:3px solid var(--brand); pointer-events:none; transition:all 200ms var(--ease); }
    .card { position:fixed; z-index:2002; width:340px; max-width:calc(100vw - 24px); background:var(--surface); color:var(--text); border-radius:var(--r3); padding:18px; box-shadow:var(--e3); outline:none; }
    .step { margin:0 0 4px; font-size:13px; color:var(--text-2); font-weight:600; }
    h2 { margin:0 0 6px; font-size:18px; line-height:1.25; }
    .body { margin:0 0 14px; font-size:14px; line-height:1.45; color:var(--text-2); }
        .foot { display:flex; flex-wrap:wrap; align-items:center; gap:8px; }
    .dots { display:inline-flex; gap:5px; flex:1; justify-content:center; } .dots i { width:7px; height:7px; border-radius:50%; background:var(--border); } .dots i.on { background:var(--brand); }
    button { min-height:44px; border-radius:10px; border:0; font:600 14px var(--rd-font-family); cursor:pointer; padding:0 14px; }
    .skip, .back { background:transparent; color:var(--text-2); } .next { background:var(--brand); color:var(--on-brand); }
    @media (prefers-reduced-motion: reduce) { .spot { transition:none; } }
  `],
})
export class TourComponent {
  readonly ui = inject(CoordUiService);
  private lang = inject(LanguageService);
  private card = viewChild<ElementRef<HTMLElement>>('card');
  /** Steps whose element is on screen when the tour opens. */
  readonly steps = signal<Step[]>([]);
  readonly index = computed(() => Math.min(this.ui.tourStep(), Math.max(0, this.steps().length - 1)));
  readonly current = computed(() => this.steps()[this.index()] || null);
  readonly rect = signal<{ top: number; left: number; width: number; height: number } | null>(null);
  readonly cardPos = signal({ top: 80, left: 80 });

  constructor() {
    effect(() => {
      if (!this.ui.tourOpen()) return;
      this.ui.tourStep();
      setTimeout(() => {
        if (!this.steps().length) {
          const live = TOUR_STEPS.filter((s) => tourAnchor(s.target));
          if (!live.length) { this.ui.finishTour(); return; }
          this.steps.set(live);
        }
        this.place(true);
        this.card()?.nativeElement.focus();
      }, 30);
    });
    effect(() => { if (!this.ui.tourOpen()) this.steps.set([]); });
  }

  last = () => this.index() >= this.steps().length - 1;
  stepLabel(): string {
    this.lang.currentLang();
    return this.lang.translate('tour.step').replace('{a}', String(this.index() + 1)).replace('{b}', String(this.steps().length));
  }
  go(d: number): void { this.ui.tourStep.set(Math.min(this.steps().length - 1, Math.max(0, this.index() + d))); }
  next(): void { this.last() ? this.skip() : this.go(1); }
  skip(): void { this.ui.finishTour(); }

  @HostListener('window:resize') onResize(): void { this.place(false); }

  place(scroll: boolean): void {
    const step = this.current();
    if (!this.ui.tourOpen() || !step) return;
    let el = tourAnchor(step.target);
    if (el && scroll) { el.scrollIntoView({ block: 'center', inline: 'nearest' }); el = tourAnchor(step.target); }
    const vw = window.innerWidth, vh = window.innerHeight;
    const cw = Math.min(340, vw - 24), ch = 230;
    if (!el) {
      // The element left the screen (narrow layout, case closed): no spotlight, centred card.
      this.rect.set(null);
      this.cardPos.set({ top: Math.max(12, (vh - ch) / 2), left: Math.max(12, (vw - cw) / 2) });
      return;
    }
    const r = el.getBoundingClientRect();
    const pad = 6;
    const box = { top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 };
    this.rect.set(box);
    let top = box.top + box.height + 12;
    if (top + ch > vh - 12) top = box.top - ch - 12;
    if (top < 12) top = Math.max(12, vh - ch - 12);
    const left = Math.max(12, Math.min(vw - cw - 12, box.left));
    this.cardPos.set({ top, left });
  }

  @HostListener('document:keydown', ['$event']) onKey(e: KeyboardEvent): void {
    if (!this.ui.tourOpen()) return;
    if (e.key === 'Escape') { e.preventDefault(); this.skip(); return; }
    if (e.key === 'Tab') {
      const focusables = this.card()?.nativeElement.querySelectorAll<HTMLElement>('button');
      if (!focusables?.length) return;
      const first = focusables[0], lastEl = focusables[focusables.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === this.card()?.nativeElement)) { e.preventDefault(); lastEl.focus(); }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); first.focus(); }
    }
  }
}
