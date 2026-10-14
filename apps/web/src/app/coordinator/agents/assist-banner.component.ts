import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';
import { LanguageService, RdTranslatePipe } from '@rd/shared';

@Component({
  selector: 'app-assist-banner',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './assist-banner.component.html',
  styleUrl: './assist-banner.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AssistBannerComponent {
  private readonly lang = inject(LanguageService);
  readonly count = input.required<number>();
  readonly review = output<void>();

  label(): string {
    this.lang.currentLang();
    const n = this.count();
    if (n === 1) return this.lang.translate('ux.staffLowOne');
    return this.lang.translate('ux.staffLowMany').replace('{n}', String(n));
  }
}
