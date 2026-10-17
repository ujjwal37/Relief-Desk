import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RdTranslatePipe } from '@rd/shared';

/** Gemini mark on an AI-filled field. Confidence is a title/hover only. */
@Component({
  selector: 'app-gemini-chip',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span class="chip" [attr.title]="tip()" data-testid="gemini-chip">{{ 'xfactor.geminiChip' | rdTranslate }}</span>
  `,
  styles: [`
    .chip {
      display: inline-flex; align-items: center; gap: 2px;
      margin-left: 6px; padding: 0 7px; border-radius: 999px;
      background: var(--brand-tint); color: var(--brand);
      font: 600 10px/18px var(--rd-font-family); letter-spacing: .02em;
      vertical-align: middle; cursor: help;
    }
  `],
})
export class GeminiChipComponent {
  readonly confidence = input<number | null>(null);
  readonly label = input('Gemini');

  tip(): string {
    const conf = this.confidence();
    if (conf == null || Number.isNaN(conf)) return 'Filled by Gemini';
    return `Gemini · ${Math.round(conf * 100)}% confidence`;
  }
}
