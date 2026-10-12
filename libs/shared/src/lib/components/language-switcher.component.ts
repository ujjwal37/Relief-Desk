import { RdTranslatePipe } from '../services/language.service';
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LanguageService, SUPPORTED_LANGUAGES, SupportedLang } from '../services/language.service';

@Component({
  selector: 'rd-language-switcher',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  template: `
    <div class="rd-lang-switcher" role="group" [attr.aria-label]="'ui.langSel' | rdTranslate">
      <button
        *ngFor="let opt of languages"
        type="button"
        class="lang-chip"
        [class.active]="langService.currentLang() === opt.code"
        (click)="selectLanguage(opt.code)"
        [attr.aria-pressed]="langService.currentLang() === opt.code"
      >
        {{ opt.nativeName }}
      </button>
    </div>
  `,
  styles: [`
    .rd-lang-switcher {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 9999px;
      padding: 3px 4px;
    }

    .lang-chip {
      background: transparent;
      border: none;
      color: var(--text);
      font-size: 0.85rem;
      font-weight: 700;
      min-height: 48px;
      min-width: 48px;
      padding: 8px 12px;
      border-radius: 9999px;
      cursor: pointer;
      transition: all 0.15s ease-in-out;
      font-family: inherit;

      &:hover {
        color: var(--brand);
      }

      &.active {
        background: var(--brand);
        color: var(--on-brand);
        box-shadow: var(--e1);
      }
    }
  `],
})
export class LanguageSwitcherComponent {
  readonly langService = inject(LanguageService);
  readonly languages = SUPPORTED_LANGUAGES;

  selectLanguage(code: SupportedLang): void {
    this.langService.setLanguage(code);
  }
}
