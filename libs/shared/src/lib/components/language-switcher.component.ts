import { RdTranslatePipe } from '../services/language.service';
import { Component, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LanguageService, MORE_LANGUAGES, PRIMARY_LANGUAGES, SupportedLang } from '../services/language.service';

@Component({
  selector: 'rd-language-switcher',
  standalone: true,
  imports: [CommonModule, RdTranslatePipe],
  template: `
    <div class="rd-lang-switcher" role="group" [attr.aria-label]="'ui.langSel' | rdTranslate">
      <button
        *ngFor="let opt of primary"
        type="button"
        class="lang-chip"
        [class.active]="langService.currentLang() === opt.code"
        (click)="selectLanguage(opt.code)"
        [attr.aria-pressed]="langService.currentLang() === opt.code"
        [attr.aria-label]="opt.label"
      >
        {{ opt.nativeName }}
      </button>
      <details class="more" *ngIf="more.length">
        <summary class="lang-chip">{{ 'settings.moreLangs' | rdTranslate }}</summary>
        <div class="more-menu">
          <button
            *ngFor="let opt of more"
            type="button"
            class="lang-chip"
            [class.active]="langService.currentLang() === opt.code"
            (click)="selectLanguage(opt.code)"
            [attr.aria-pressed]="langService.currentLang() === opt.code"
            [attr.aria-label]="opt.label"
          >
            {{ opt.label }}
          </button>
        </div>
      </details>
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

    .more { position: relative; }
    .more summary { list-style: none; }
    .more summary::-webkit-details-marker { display: none; }
    .more-menu {
      position: absolute;
      right: 0;
      top: calc(100% + 6px);
      display: grid;
      gap: 4px;
      min-width: 140px;
      padding: 6px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      box-shadow: var(--e2);
      z-index: 5;
    }
  `],
})
export class LanguageSwitcherComponent {
  readonly langService = inject(LanguageService);
  readonly primary = PRIMARY_LANGUAGES;
  readonly more = MORE_LANGUAGES;

  selectLanguage(code: SupportedLang): void {
    this.langService.setLanguage(code);
  }
}
