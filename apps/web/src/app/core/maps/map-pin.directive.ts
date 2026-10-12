import { Directive, ElementRef, Input, OnChanges, inject } from '@angular/core';
import { PinSpec, buildPinGroup } from './map-pins';

/** Draws a pin into an SVG `<g>`. A custom element inside `<svg>` would not render. */
@Directive({
  selector: 'g[rdPin]',
  standalone: true,
})
export class MapPinDirective implements OnChanges {
  private host = inject(ElementRef<SVGGElement>);

  @Input({ required: true }) rdPin!: PinSpec;

  ngOnChanges(): void {
    if (!this.rdPin) return;
    this.host.nativeElement.replaceChildren(buildPinGroup(this.rdPin));
  }
}
