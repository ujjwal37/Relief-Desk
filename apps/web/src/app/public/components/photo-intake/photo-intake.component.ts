import { ChangeDetectionStrategy, Component, OnDestroy, inject, input, output, signal } from '@angular/core';
import { Subscription, timeout } from 'rxjs';
import { ApiClientService, LanguageService, PhotoAnalysis, PhotoReading, RdTranslatePipe } from '@rd/shared';

@Component({
  selector: 'app-photo-intake',
  standalone: true,
  imports: [RdTranslatePipe],
  templateUrl: './photo-intake.component.html',
  styleUrl: './photo-intake.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PhotoIntakeComponent implements OnDestroy {
  private readonly api = inject(ApiClientService);
  private readonly lang = inject(LanguageService);
  readonly caption = input('');
  readonly online = input(true);
  readonly accepted = output<string>();
  readonly preview = signal('');
  readonly mime = signal('');
  readonly synthetic = signal(false);
  readonly reviewed = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly result = signal<PhotoAnalysis | null>(null);
  private generation = 0;
  private request?: Subscription;
  private reader?: FileReader;

  selectFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.clear();
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      this.error.set('photo.invalid');
      return;
    }
    const ticket = this.generation;
    this.mime.set(file.type);
    this.reader = new FileReader();
    this.reader.onload = () => {
      if (ticket === this.generation) this.preview.set(String(this.reader?.result || ''));
    };
    this.reader.onerror = () => this.error.set('photo.invalid');
    this.reader.readAsDataURL(file);
  }

  analyse(): void {
    if (!this.preview() || !this.synthetic() || !this.online() || this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    this.result.set(null);
    this.reviewed.set(false);
    const ticket = this.generation;
    const raw = this.preview().split(',')[1] || '';
    const send = (image_base64: string, mime_type: 'image/jpeg' | 'image/png' | 'image/webp') => {
      if (ticket !== this.generation) return;
      this.request = this.api.analysePhoto({
        image_base64,
        mime_type,
        caption: this.caption().slice(0, 1000),
        synthetic: true,
      }).pipe(timeout(50000)).subscribe({
        next: (result) => {
          if (ticket !== this.generation) return;
          this.busy.set(false);
          this.result.set(result);
          if (!result.reading) this.error.set('photo.unavailable');
        },
        error: () => {
          if (ticket !== this.generation) return;
          this.busy.set(false);
          this.error.set('photo.unavailable');
        },
      });
    };
    if (raw.length < 200) {
      send(raw, this.mime() as 'image/jpeg' | 'image/png' | 'image/webp');
      return;
    }
    void jpegMax(this.preview()).then((out) => send(out.b64, out.mime));
  }

  readingText(reading: PhotoReading): string {
    this.lang.currentLang();
    return `${this.lang.translate('photo.water.' + reading.water_level)}; ${this.lang.translate('photo.damage.' + reading.structural_damage)}`;
  }

  accept(): void {
    const reading = this.result()?.reading;
    if (!reading || !this.reviewed()) return;
    this.accepted.emit(this.lang.translate('photo.confirmedWords').replace('{observations}', this.readingText(reading)));
    this.clear();
  }

  clear(): void {
    this.generation += 1;
    this.request?.unsubscribe();
    this.reader?.abort();
    this.preview.set('');
    this.result.set(null);
    this.synthetic.set(false);
    this.reviewed.set(false);
    this.busy.set(false);
    this.error.set('');
  }

  ngOnDestroy(): void { this.clear(); }
}

function jpegMax(dataUrl: string, maxPx = 768): Promise<{ b64: string; mime: 'image/jpeg' }> {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxPx / Math.max(img.width || 1, img.height || 1));
      const canvas = document.createElement('canvas');
      canvas.width = Math.max(1, Math.round(img.width * scale));
      canvas.height = Math.max(1, Math.round(img.height * scale));
      const ctx = canvas.getContext('2d');
      if (!ctx) {
        resolve({ b64: dataUrl.split(',')[1] || '', mime: 'image/jpeg' });
        return;
      }
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      const out = canvas.toDataURL('image/jpeg', 0.7);
      resolve({ b64: out.split(',')[1] || '', mime: 'image/jpeg' });
    };
    img.onerror = () => resolve({ b64: dataUrl.split(',')[1] || '', mime: 'image/jpeg' });
    img.src = dataUrl;
  });
}
