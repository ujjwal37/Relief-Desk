import { Injectable, signal, computed, Pipe, PipeTransform } from '@angular/core';
import enJson from '../i18n/en.json';
import hiJson from '../i18n/hi.json';
import hinglishJson from '../i18n/hinglish.json';
import mlJson from '../i18n/ml.json';

export type SupportedLang = 'en' | 'hi' | 'hinglish' | 'ml';

export interface LangOption {
  code: SupportedLang;
  label: string;
  nativeName: string;
}

export const SUPPORTED_LANGUAGES: LangOption[] = [
  { code: 'en', label: 'English', nativeName: 'EN' },
  { code: 'hi', label: 'Hindi', nativeName: 'हिंदी' },
  { code: 'hinglish', label: 'Hinglish', nativeName: 'Hinglish' },
  { code: 'ml', label: 'Malayalam', nativeName: 'മലയാളം' },
];

/** Shown without opening More. */
export const PRIMARY_LANGUAGES: LangOption[] = SUPPORTED_LANGUAGES.filter((l) => l.code === 'en' || l.code === 'hi');

/** Hinglish and Malayalam stay available behind More. */
export const MORE_LANGUAGES: LangOption[] = SUPPORTED_LANGUAGES.filter((l) => l.code === 'hinglish' || l.code === 'ml');

const DICTIONARIES: Record<SupportedLang, any> = {
  en: enJson,
  hi: hiJson,
  hinglish: hinglishJson,
  ml: mlJson,
};

@Injectable({
  providedIn: 'root',
})
export class LanguageService {
  readonly currentLang = signal<SupportedLang>('en');

  constructor() {
    const stored = localStorage.getItem('rd_preferred_lang');
    const saved = (stored === 'ta' ? 'en' : stored) as SupportedLang;
    if (saved && DICTIONARIES[saved]) {
      this.setLanguage(saved);
    }
  }

  setLanguage(lang: SupportedLang): void {
    if (DICTIONARIES[lang]) {
      this.currentLang.set(lang);
      try {
        localStorage.setItem('rd_preferred_lang', lang);
        if (typeof document !== 'undefined') {
          document.documentElement.lang = lang === 'hinglish' ? 'hi-Latn' : lang;
        }
      } catch (e) {
        // Safe for non-browser/test environments
      }
    }
  }

  translate(key: string, params?: Record<string, any>): string {
    const lang = this.currentLang();
    const dict = DICTIONARIES[lang] || DICTIONARIES['en'];
    const resolve = (d: any, k: string): string | null => {
      if (!d || typeof d !== 'object') return null;
      if (k in d && typeof d[k] === 'string') return d[k];
      const parts = k.split('.');
      let val: any = d;
      for (let i = 0; i < parts.length; i++) {
        if (!val || typeof val !== 'object') return null;
        const rest = parts.slice(i).join('.');
        if (rest in val && typeof val[rest] === 'string') return val[rest];
        const part = parts[i];
        if (part in val) {
          val = val[part];
        } else {
          return null;
        }
      }
      return typeof val === 'string' ? val : null;
    };
    let text = resolve(dict, key) ?? resolve(DICTIONARIES['en'], key) ?? key;
    if (params && typeof text === 'string') {
      for (const [pk, pv] of Object.entries(params)) {
        text = text.replaceAll(`{${pk}}`, String(pv));
      }
    }
    return text;
  }
}

@Pipe({
  name: 'rdTranslate',
  standalone: true,
  pure: false,
})
export class RdTranslatePipe implements PipeTransform {
  constructor(private langService: LanguageService) {}

  transform(key: string, params?: Record<string, any>): string {
    // Read reactive signal to automatically re-trigger on language change
    this.langService.currentLang();
    return this.langService.translate(key, params);
  }
}
