import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RdTranslatePipe } from '../services/language.service';

/** Small outlined Call 112 button. Replaces the old red emergency banner. */
@Component({
  selector: 'rd-call-pill',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<a href="tel:112" class="pill"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1 1 .4 1.9.7 2.8a2 2 0 0 1-.5 2.1L8 9.9a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.8.7a2 2 0 0 1 1.7 2z"/></svg><span>{{ 'safety.call112' | rdTranslate }}</span><span class="digits">112</span></a>`,
  styles: [`
    .pill { display:inline-flex; align-items:center; gap:6px; min-height:44px; padding:0 14px; border:1.5px solid var(--sos-text); color:var(--sos-text);
      border-radius:999px; font:700 15px/1 var(--rd-font-family); text-decoration:none; background:transparent; white-space:nowrap; }
    .digits { font-variant-numeric:tabular-nums; letter-spacing:.02em; }
    .pill:focus-visible { outline:3px solid var(--focus); outline-offset:2px; }
  `],
})
export class CallPillComponent {}
