import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LanguageService, SUPPORTED_LANGUAGES, SupportedLang } from '../services/language.service';

@Component({
  selector: 'rd-language-switcher',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="rd-lang-switcher" role="group" aria-label="Language selection">
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
      background: rgba(15, 23, 42, 0.6);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 9999px;
      padding: 3px 4px;
    }

    .lang-chip {
      background: transparent;
      border: none;
      color: #94a3b8;
      font-size: 0.78rem;
      font-weight: 600;
      padding: 3px 9px;
      border-radius: 9999px;
      cursor: pointer;
      transition: all 0.15s ease-in-out;
      font-family: inherit;

      &:hover {
        color: #ffffff;
      }

      &.active {
        background: #0f6b5a;
        color: #ffffff;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3);
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
