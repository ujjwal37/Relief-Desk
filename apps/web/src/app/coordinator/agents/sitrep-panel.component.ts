import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { RdTranslatePipe, SitrepResponse } from '@rd/shared';

@Component({
  selector: 'app-sitrep-panel',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="scrim" (click)="closed.emit()"></div>
    <aside class="panel" role="dialog" aria-modal="true" aria-labelledby="sitrep-h">
      <header>
        <h2 id="sitrep-h">{{ 'xfactor.sitrepTitle' | rdTranslate }}</h2>
        <button type="button" class="x" (click)="closed.emit()" [attr.aria-label]="'ux.close' | rdTranslate">✕</button>
      </header>
      @if (busy()) { <p class="note">{{ 'xfactor.sitrepBusy' | rdTranslate }}</p> }
      @if (error()) { <p class="err">{{ 'xfactor.sitrepError' | rdTranslate }}</p> }
      @if (report(); as r) {
        <p class="src">{{ r.ai.provider === 'gemini' ? ('xfactor.geminiLive' | rdTranslate) : ('xfactor.rulesFallback' | rdTranslate) }}
          @if (r.cached) { · {{ 'xfactor.cached' | rdTranslate }} }</p>
        <p class="brief">{{ r.brief }}</p>
        <ul class="counts">
          <li>{{ 'xfactor.pending' | rdTranslate }} {{ r.counts.pending }}</li>
          <li>{{ 'xfactor.tierImmediate' | rdTranslate }} {{ r.counts.by_tier['immediate'] || 0 }}</li>
          <li>{{ 'xfactor.tierUrgent' | rdTranslate }} {{ r.counts.by_tier['urgent'] || 0 }}</li>
          <li>{{ 'xfactor.boats' | rdTranslate }} {{ r.counts.free_boats }}</li>
          <li>{{ 'xfactor.rooftop' | rdTranslate }} {{ r.counts.rooftop_like }}</li>
        </ul>
        @if (r.counts.gaps.length) {
          <p class="gap">{{ r.counts.gaps[0] }}</p>
        }
        <p class="draft-note">{{ 'xfactor.draftOnly' | rdTranslate }}</p>
        @for (key of draftKeys; track key) {
          <div class="draft">
            <div class="dhead">
              <span>{{ key }}</span>
              <button type="button" (click)="copy(key, r.drafts[key])">{{ copied() === key ? ('xfactor.copied' | rdTranslate) : ('xfactor.copy' | rdTranslate) }}</button>
            </div>
            <pre>{{ r.drafts[key] }}</pre>
          </div>
        }
      }
    </aside>
  `,
  styles: [`
    .scrim { position:fixed; inset:0; z-index:2100; background:var(--scrim, rgba(0,0,0,.35)); }
    .panel { position:fixed; z-index:2101; top:0; right:0; width:min(420px,100vw); height:100%; overflow:auto;
      background:var(--surface); color:var(--text); border-left:1px solid var(--border); padding:16px 18px 28px; box-shadow:var(--e3); }
    header { display:flex; align-items:center; gap:8px; }
    h2 { flex:1; margin:0; font-size:18px; }
    .x { border:0; background:transparent; font-size:18px; cursor:pointer; color:inherit; min-height:44px; min-width:44px; }
    .brief, .gap, .note, .draft-note { font-size:14px; line-height:1.45; color:var(--text-2); }
    .src { font-size:12px; font-weight:600; color:var(--brand); }
    .counts { display:flex; flex-wrap:wrap; gap:6px; padding:0; margin:10px 0; list-style:none; }
    .counts li { padding:4px 8px; border-radius:999px; background:var(--surface-2); font-size:12px; }
    .draft { margin:10px 0; }
    .dhead { display:flex; justify-content:space-between; font-size:12px; font-weight:600; }
    .dhead button { border:0; background:transparent; color:var(--brand); cursor:pointer; font:inherit; }
    pre { white-space:pre-wrap; margin:4px 0 0; padding:8px; border-radius:8px; background:var(--surface-2); font:13px/1.4 var(--rd-font-family); }
    .err { color:var(--sos-text, #b42318); }
  `],
})
export class SitrepPanelComponent {
  readonly report = input<SitrepResponse | null>(null);
  readonly busy = input(false);
  readonly error = input(false);
  readonly closed = output<void>();
  readonly copied = signal('');
  readonly draftKeys = ['sms_en', 'sms_hi', 'sms_ml', 'whatsapp_en', 'whatsapp_hi', 'whatsapp_ml'] as const;

  copy(key: string, text: string): void {
    if (!text || typeof navigator === 'undefined' || !navigator.clipboard) return;
    void navigator.clipboard.writeText(text).then(() => {
      this.copied.set(key);
      setTimeout(() => this.copied.set(''), 1200);
    });
  }
}
