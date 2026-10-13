import { ChangeDetectionStrategy, Component, ElementRef, HostListener, effect, inject, signal, viewChild } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';
import { CoordUiService } from '../services/coord-ui.service';

interface Step { target: string; title: string; body: string; }
const STEPS: Step[] = [
  { target: 'cases', title: 'tour.s1t', body: 'tour.s1b' },
  { target: 'detail', title: 'tour.s2t', body: 'tour.s2b' },
  { target: 'actions', title: 'tour.s3t', body: 'tour.s3b' },
];

/** Guided tour: spotlight + tooltip card. Focus-trapped, Esc closes, no library. */
@Component({
  selector: 'app-tour',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (ui.tourOpen()) {
      <div class="shade" (click)="skip()"></div>
      <div class="spot" [style.top.px]="rect().top" [style.left.px]="rect().left" [style.width.px]="rect().width" [style.height.px]="rect().height"></div>
      <div class="card" role="dialog" aria-modal="true" aria-live="polite" [attr.aria-label]="steps[ui.tourStep()].title | rdTranslate" #card tabindex="-1"
        [style.top.px]="cardPos().top" [style.left.px]="cardPos().left">
        <p class="step">{{ stepLabel() }}</p>
        <h2>{{ steps[ui.tourStep()].title | rdTranslate }}</h2>
        <p class="body">{{ steps[ui.tourStep()].body | rdTranslate }}</p>
        <div class="foot">
          <button type="button" class="skip" (click)="skip()">{{ 'coord.dismissTour' | rdTranslate }}</button>
          <span class="dots" aria-hidden="true">@for (s of steps; track $index) { <i [class.on]="$index === ui.tourStep()"></i> }</span>
          @if (ui.tourStep() > 0) { <button type="button" class="back" (click)="go(-1)">{{ 'tour.back' | rdTranslate }}</button> }
          <button type="button" class="next" (click)="next()">{{ (last() ? 'tour.done' : 'tour.next') | rdTranslate }} @if (!last()) {→}</button>
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
    .foot { display:flex; align-items:center; gap:8px; }
    .dots { display:inline-flex; gap:5px; flex:1; justify-content:center; } .dots i { width:7px; height:7px; border-radius:50%; background:var(--border); } .dots i.on { background:var(--brand); }
    button { min-height:44px; border-radius:10px; border:0; font:600 14px var(--rd-font-family); cursor:pointer; padding:0 14px; }
    .skip, .back { background:transparent; color:var(--text-2); } .next { background:var(--brand); color:var(--on-brand); }
    @media (prefers-reduced-motion: reduce) { .spot { transition:none; } }
  `],
})
export class TourComponent {
  readonly ui = inject(CoordUiService);
  readonly steps = STEPS;
  private lang = inject(LanguageService);
  private card = viewChild<ElementRef<HTMLElement>>('card');
  readonly rect = signal({ top: 0, left: 0, width: 0, height: 0 });
  readonly cardPos = signal({ top: 80, left: 80 });

  constructor() {
    effect(() => {
      if (this.ui.tourOpen()) {
        this.ui.tourStep();
        setTimeout(() => { this.place(); this.card()?.nativeElement.focus(); }, 30);
      }
    });
  }

  last = () => this.ui.tourStep() === STEPS.length - 1;
  stepLabel(): string {
    return this.lang.translate('tour.step').replace('{a}', String(this.ui.tourStep() + 1)).replace('{b}', String(STEPS.length));
  }
  go(d: number): void { this.ui.tourStep.update((s) => Math.min(STEPS.length - 1, Math.max(0, s + d))); }
  next(): void { this.last() ? this.skip() : this.go(1); }
  skip(): void { this.ui.finishTour(); }

  @HostListener('window:resize') place(): void {
    if (!this.ui.tourOpen()) return;
    const el = document.querySelector(`[data-tour="${STEPS[this.ui.tourStep()].target}"]`) as HTMLElement | null;
    const r = el?.getBoundingClientRect();
    const pad = 6;
    const box = r ? { top: r.top - pad, left: r.left - pad, width: r.width + pad * 2, height: r.height + pad * 2 } : { top: 0, left: 0, width: 0, height: 0 };
    this.rect.set(box);
    const cw = 340, ch = 220, vw = window.innerWidth, vh = window.innerHeight;
    let left = box.left + box.width + 16;
    if (left + cw > vw - 12) left = box.left - cw - 16;
    if (left < 12) left = Math.max(12, Math.min(vw - cw - 12, box.left + 16));
    const top = Math.max(12, Math.min(vh - ch - 12, box.top + 16));
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
