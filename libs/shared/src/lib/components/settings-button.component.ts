import { ChangeDetectionStrategy, Component, ElementRef, HostListener, inject, signal, viewChild } from '@angular/core';
import { LanguageService, RdTranslatePipe, SUPPORTED_LANGUAGES, SupportedLang } from '../services/language.service';
import { ThemeMode, ThemeService } from '../services/theme.service';

/** Globe button that opens a bottom sheet (language + theme). Shared by public and coordinator apps. */
@Component({
  selector: 'rd-settings-button',
  standalone: true,
  imports: [RdTranslatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="rd-set-btn" (click)="open()" [attr.aria-label]="'settings.title' | rdTranslate" aria-haspopup="dialog">
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3.2 3 14.8 0 18M12 3c-3 3.2-3 14.8 0 18"/></svg>
      @if (showCode()) { <span class="code">{{ langCode() }}</span> }
    </button>
    @if (isOpen()) {
      <div class="rd-backdrop" (click)="close()"></div>
      <div class="rd-sheet" role="dialog" aria-modal="true" [attr.aria-label]="'settings.title' | rdTranslate" #sheet tabindex="-1">
        <div class="grab" aria-hidden="true"></div>
        <h2>{{ 'settings.title' | rdTranslate }}</h2>
        <h3>{{ 'settings.language' | rdTranslate }}</h3>
        <div class="opts">
          @for (l of langs; track l.code) {
            <button type="button" class="opt" [class.on]="lang.currentLang() === l.code" [attr.aria-pressed]="lang.currentLang() === l.code" (click)="setLang(l.code)">
              {{ l.label }} <span class="native">{{ l.nativeName }}</span>
            </button>
          }
        </div>
        <h3>{{ 'settings.theme' | rdTranslate }}</h3>
        <div class="seg" role="group">
          @for (t of themes; track t.m) {
            <button type="button" [class.on]="theme.mode() === t.m" [attr.aria-pressed]="theme.mode() === t.m" (click)="theme.setMode(t.m)">{{ t.k | rdTranslate }}</button>
          }
        </div>
        <button type="button" class="done" (click)="close()">{{ 'settings.close' | rdTranslate }}</button>
      </div>
    }
  `,
  styles: [`
    :host { display: inline-flex; }
    .rd-set-btn { display:inline-flex; align-items:center; gap:6px; min-height:44px; min-width:44px; padding:0 10px; justify-content:center;
      background:var(--surface); color:var(--text); border:1px solid var(--border); border-radius:999px; font:600 15px/1 var(--rd-font-family); cursor:pointer; }
    .rd-set-btn:focus-visible, .opt:focus-visible, .seg button:focus-visible, .done:focus-visible { outline:3px solid var(--focus); outline-offset:2px; }
    .rd-backdrop { position:fixed; inset:0; background:var(--scrim); z-index:1000; animation: fade 200ms var(--ease); }
    .rd-sheet { position:fixed; z-index:1001; left:0; right:0; bottom:0; max-width:480px; margin:0 auto; background:var(--surface); color:var(--text);
      border-radius:24px 24px 0 0; padding:12px 20px calc(20px + env(safe-area-inset-bottom)); box-shadow:var(--e3); animation: up 200ms var(--ease); outline:none; }
    .grab { width:40px; height:4px; border-radius:2px; background:var(--border); margin:0 auto 12px; }
    h2 { margin:0 0 8px; font-size:22px; } h3 { margin:16px 0 8px; font-size:15px; color:var(--text-2); font-weight:600; }
    .opts { display:grid; gap:8px; }
    .opt { display:flex; justify-content:space-between; align-items:center; min-height:52px; padding:0 16px; border-radius:12px; border:1px solid var(--border);
      background:var(--surface); color:var(--text); font:600 17px var(--rd-font-family); cursor:pointer; }
    .opt.on { border:2px solid var(--brand); background:var(--brand-tint); }
    .native { color:var(--text-2); font-weight:500; }
    .seg { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; background:var(--surface-2); padding:4px; border-radius:12px; }
    .seg button { min-height:48px; border:0; border-radius:9px; background:transparent; color:var(--text); font:600 16px var(--rd-font-family); cursor:pointer; }
    .seg button.on { background:var(--surface); box-shadow:var(--e1); color:var(--brand); }
    .done { width:100%; margin-top:20px; min-height:52px; border:0; border-radius:12px; background:var(--brand); color:var(--on-brand); font:700 18px var(--rd-font-family); cursor:pointer; }
    @keyframes up { from { transform:translateY(24px); opacity:0 } to { transform:none; opacity:1 } }
    @keyframes fade { from { opacity:0 } to { opacity:1 } }
    @media (prefers-reduced-motion: reduce) { .rd-sheet, .rd-backdrop { animation: fade 1ms; } }
  `],
})
export class SettingsButtonComponent {
  readonly lang = inject(LanguageService);
  readonly theme = inject(ThemeService);
  readonly langs = SUPPORTED_LANGUAGES;
  readonly themes: { m: ThemeMode; k: string }[] = [
    { m: 'system', k: 'settings.themeSystem' }, { m: 'light', k: 'settings.themeLight' }, { m: 'dark', k: 'settings.themeDark' },
  ];
  readonly isOpen = signal(false);
  private sheet = viewChild<ElementRef<HTMLElement>>('sheet');
  private opener: HTMLElement | null = null;

  showCode = () => true;
  langCode = () => ({ en: 'EN', hi: 'HI', hinglish: 'HG', ml: 'ML' }[this.lang.currentLang()]);

  open(): void {
    this.opener = document.activeElement as HTMLElement;
    this.isOpen.set(true);
    setTimeout(() => this.sheet()?.nativeElement.focus());
  }
  close(): void { this.isOpen.set(false); this.opener?.focus(); }
  setLang(c: SupportedLang): void { this.lang.setLanguage(c); }
  @HostListener('document:keydown.escape') onEsc(): void { if (this.isOpen()) this.close(); }
}
