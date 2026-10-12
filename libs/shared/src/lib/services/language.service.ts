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
  { code: 'hi', label: 'Hindi', nativeName: 'हिन्दी' },
  { code: 'hinglish', label: 'Hinglish', nativeName: 'Hinglish' },
  { code: 'ml', label: 'Malayalam', nativeName: 'മലയാളം' },
];

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
    const saved = (stored === 'ta' ? 'ml' : stored) as SupportedLang;
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

  translate(key: string): string {
    const lang = this.currentLang();
    const dict = DICTIONARIES[lang] || DICTIONARIES['en'];
    const parts = key.split('.');
    let val: any = dict;
    for (const part of parts) {
      if (val && typeof val === 'object' && part in val) {
        val = val[part];
      } else {
        // Fallback to English
        let fallbackVal: any = DICTIONARIES['en'];
        for (const fbPart of parts) {
          if (fallbackVal && typeof fallbackVal === 'object' && fbPart in fallbackVal) {
            fallbackVal = fallbackVal[fbPart];
          } else {
            return key;
          }
        }
        return typeof fallbackVal === 'string' ? fallbackVal : key;
      }
    }
    return typeof val === 'string' ? val : key;
  }
}

@Pipe({
  name: 'rdTranslate',
  standalone: true,
  pure: false,
})
export class RdTranslatePipe implements PipeTransform {
  constructor(private langService: LanguageService) {}

  transform(key: string): string {
    // Read reactive signal to automatically re-trigger on language change
    this.langService.currentLang();
    return this.langService.translate(key);
  }
}
