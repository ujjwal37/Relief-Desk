import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RdTranslatePipe } from '@rd/shared';
import type { UrgencyBandKey } from '@rd/shared';

/** Severity chip: icon + word + colour (never colour alone). */
@Component({
  selector: 'app-sev-chip',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [class]="band()">
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        @switch (band()) {
          @case ('critical') { <path d="M12 3 2 21h20L12 3z"/><path d="M12 10v5M12 18v.5"/> }
          @case ('high') { <circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/> }
          @case ('medium') { <circle cx="12" cy="12" r="4"/> }
          @default { <path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="2.5"/> }
        }
      </svg>
      {{ 'coord.band.' + band() | rdTranslate }}
    </span>
  `,
  styles: [`
    .chip { display:inline-flex; align-items:center; gap:4px; padding:2px 10px; border-radius:var(--r2); border:1px solid transparent; font:600 12px/1.25 var(--rd-font-family); white-space:nowrap; }
    .critical { background:var(--sev-crit-t); color:var(--sev-crit); }
    .high { background:var(--sev-high-t); color:var(--sev-high); }
    .medium { background:var(--sev-med-t); color:var(--sev-med); }
    .low { background:var(--surface-2); color:var(--text-2); }
  `],
})
export class SevChipComponent {
  readonly band = input.required<UrgencyBandKey>();
}
