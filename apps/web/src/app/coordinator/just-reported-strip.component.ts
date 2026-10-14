import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, computed, inject, output, signal } from '@angular/core';
import { LanguageService, RdTranslatePipe, RecentReport } from '@rd/shared';
import { minutesAgo, visibleReports, wardText } from './just-reported';
import { JustReportedService } from './just-reported.service';

/** Compact strip of reports from the last 15 minutes. */
@Component({
  selector: 'app-just-reported',
  standalone: true,
  imports: [RdTranslatePipe],
  template: `
    @if (rows().length) {
      <section class="just" data-testid="just-reported" [attr.aria-label]="'coord.justReported' | rdTranslate">
        <h2>{{ 'coord.justReported' | rdTranslate }}</h2>
        <div class="row">
          @for (item of rows(); track item.id) {
            <button type="button" class="chip" [attr.data-case-id]="item.case_id" (click)="picked.emit(item.case_id)">
              <span class="ico" [attr.data-type]="item.type" aria-hidden="true">
                @switch (item.type) {
                  @case ('medical') {
                    <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z"/></svg>
                  }
                  @case ('food') {
                    <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M4 10h16v2a8 8 0 0 1-16 0zm2 10h12v2H6z"/></svg>
                  }
                  @case ('shelter') {
                    <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M12 3 3 11h2v9h6v-6h2v6h6v-9h2z"/></svg>
                  }
                  @case ('animal_attack') {
                    <svg viewBox="0 0 24 24" width="18" height="18"><circle cx="7" cy="7" r="2.2" fill="currentColor"/><circle cx="12" cy="5" r="2.2" fill="currentColor"/><circle cx="17" cy="7" r="2.2" fill="currentColor"/><ellipse cx="12" cy="15" rx="5" ry="4" fill="currentColor"/></svg>
                  }
                  @default {
                    <svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M3 14c2 0 2-3 4-3s2 3 4 3 2-3 4-3 2 3 4 3v3H3z"/></svg>
                  }
                }
              </span>
              <span class="copy">
                <span class="sum">{{ item.summary }}</span>
                <span class="meta">
                  @if (ward(item)) { <span>{{ ward(item) }}</span> }
                  <span>{{ ago(item) }}</span>
                  <span class="badge">{{ 'coord.justNew' | rdTranslate }}</span>
                </span>
                @if (item.joined_existing) {
                  <span class="merge">{{ 'coord.justJoined' | rdTranslate }}</span>
                }
              </span>
            </button>
          }
        </div>
      </section>
    }
    @if (store.toast()) {
      <div class="arrival-toast" role="status">{{ store.toast() }}</div>
    }
  `,
  styles: [`
    :host { display: block; flex: none; }
    .just { padding: 6px 12px 0; }
    h2 { margin: 0 0 4px; font-size: 13px; font-weight: 600; letter-spacing: -0.01em; color: var(--muted); }
    .row { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 2px; }
    .chip {
      flex: none; display: flex; gap: 6px; align-items: flex-start; max-width: 240px;
      min-height: 40px; text-align: left; border: 1px solid var(--border); border-radius: 12px;
      background: var(--surface); color: var(--text); padding: 4px 8px; cursor: pointer;
      font: 400 13px/1.35 var(--rd-font-family);
    }
    .ico { flex: none; width: 28px; height: 28px; border-radius: 8px; display: grid; place-items: center; background: var(--brand-tint); color: var(--brand); }
    .ico[data-type="medical"] { color: var(--sev-crit); background: var(--sev-crit-t); }
    .ico[data-type="food"] { color: var(--sev-high); background: var(--sev-high-t, var(--brand-tint)); }
    .ico[data-type="shelter"] { color: var(--ok); background: var(--ok-t); }
    .copy { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
    .sum { display: block; font-weight: 600; font-size: 14px; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 210px; }
    .meta { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; font-size: 12px; font-weight: 400; color: var(--muted); }
    .badge { background: var(--brand-tint); color: var(--brand); border-radius: var(--r2); padding: 0 6px; font-weight: 600; font-size: 12px; }
    .merge { font-size: 12px; font-weight: 600; color: var(--text-2); }
    .arrival-toast {
      position: fixed; left: 50%; bottom: 24px; transform: translateX(-50%); z-index: 1600;
      max-width: min(560px, 92vw); background: var(--text); color: var(--bg);
      padding: 12px 16px; border-radius: 12px; box-shadow: var(--e3);
      font-size: 14px; font-weight: 600;
    }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JustReportedStripComponent implements OnInit, OnDestroy {
  private readonly lang = inject(LanguageService);
  readonly store = inject(JustReportedService);
  readonly picked = output<string>();
  private readonly now = signal(Date.now());
  private clock: ReturnType<typeof setInterval> | null = null;

  readonly rows = computed(() => {
    this.lang.currentLang();
    return visibleReports(this.store.items(), this.now()).slice(0, 3);
  });

  ngOnInit(): void {
    this.store.retain();
    this.clock = setInterval(() => this.now.set(Date.now()), 30_000);
  }

  ngOnDestroy(): void {
    if (this.clock) clearInterval(this.clock);
    this.store.release();
  }

  ward(item: RecentReport): string {
    return wardText(item.ward_id, this.lang.currentLang());
  }

  ago(item: RecentReport): string {
    const mins = minutesAgo(item.created_at, this.now());
    if (mins < 1) return this.lang.translate('coord.justNow');
    return this.lang.translate('coord.minAgo').replace('{n}', String(mins));
  }
}
