import { CommonModule } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  ElementRef,
  EventEmitter,
  Input,
  OnChanges,
  OnDestroy,
  Output,
  ViewChild,
  inject,
} from '@angular/core';
import { MapProviderService } from './map-provider.service';

export interface MapPin {
  id: string;
  lat: number;
  lng: number;
  title: string;
}

@Component({
  selector: 'rd-map-provider',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (mode === 'google') {
      <div #canvas class="rd-google-map" role="application" aria-label="Riverbend map"></div>
    } @else {
      <ng-content></ng-content>
    }
  `,
  styles: [`
    :host { display: block; width: 100%; height: 100%; min-height: 250px; position: relative; }
    .rd-google-map { width: 100%; height: 100%; min-height: 250px; }
  `],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MapProviderComponent implements AfterViewInit, OnChanges, OnDestroy {
  private maps = inject(MapProviderService);
  private cdr = inject(ChangeDetectorRef);

  @Input() pins: MapPin[] = [];
  @Input() center: { lat: number; lng: number } = { lat: 26.852, lng: 80.925 };
  @Output() pinSelect = new EventEmitter<string>();

  @ViewChild('canvas') canvas?: ElementRef<HTMLDivElement>;

  mode: 'google' | 'svg' = 'svg';
  private map: { panTo?: (pos: { lat: number; lng: number }) => void } | null = null;
  private markers: { setMap?: (map: null) => void }[] = [];

  ngAfterViewInit(): void {
    this.maps.decide().then((mode) => {
      this.mode = mode;
      this.cdr.detectChanges();
      if (mode === 'google') {
        this.draw();
      }
    });
    window.addEventListener('offline', this.onOffline);
  }

  ngOnDestroy(): void {
    window.removeEventListener('offline', this.onOffline);
  }

  ngOnChanges(): void {
    if (this.mode === 'google' && this.map) {
      this.draw();
    }
  }

  private onOffline = (): void => {
    this.mode = 'svg';
    this.map = null;
    this.cdr.markForCheck();
  };

  private draw(): void {
    const el = this.canvas?.nativeElement;
    const google = (window as unknown as { google?: { maps?: GoogleMapsNs } }).google;
    const maps = google?.maps;
    if (!el || !maps) {
      this.mode = 'svg';
      this.cdr.markForCheck();
      return;
    }
    try {
      if (!this.map) {
        this.map = new maps.Map(el, {
          center: this.center,
          zoom: 13,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: false,
        });
      }
      this.markers.forEach((marker) => marker.setMap?.(null));
      this.markers = this.pins.map((pin) => {
        const marker = new maps.Marker({
          map: this.map,
          position: { lat: pin.lat, lng: pin.lng },
          title: pin.title,
        });
        marker.addListener?.('click', () => this.pinSelect.emit(pin.id));
        return marker;
      });
    } catch {
      this.mode = 'svg';
      this.map = null;
      this.cdr.markForCheck();
    }
  }
}

interface GoogleMapsNs {
  Map: new (el: HTMLElement, opts: Record<string, unknown>) => { panTo?: (pos: { lat: number; lng: number }) => void };
  Marker: new (opts: Record<string, unknown>) => { setMap?: (map: null) => void; addListener?: (event: string, fn: () => void) => void };
}
