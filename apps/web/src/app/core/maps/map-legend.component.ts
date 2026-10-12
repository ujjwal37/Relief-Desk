import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RdTranslatePipe } from '@rd/shared';
import { MapPinDirective } from './map-pin.directive';
import { PinSpec } from './map-pins';

@Component({
  selector: 'rd-map-legend',
  standalone: true,
  imports: [RdTranslatePipe, MapPinDirective],
  templateUrl: './map-legend.component.html',
  styleUrl: './map-legend.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MapLegendComponent {
  readonly critical: PinSpec = { kind: 'case', severity: 'critical', queue: 1 };
  readonly high: PinSpec = { kind: 'case', severity: 'high', queue: 3 };
  readonly medium: PinSpec = { kind: 'case', severity: 'medium', queue: 5 };
  readonly low: PinSpec = { kind: 'case', severity: 'low', queue: 6 };
  readonly merged: PinSpec = { kind: 'case', severity: 'critical', queue: 2, merged: 3 };
  readonly boat: PinSpec = { kind: 'team', team: 'boat', free: true };
  readonly ambulance: PinSpec = { kind: 'team', team: 'ambulance', free: true };
  readonly medic: PinSpec = { kind: 'team', team: 'medic', free: true };
  readonly food: PinSpec = { kind: 'team', team: 'food', free: true };
  readonly rescue: PinSpec = { kind: 'team', team: 'rescue', free: true };
  readonly busy: PinSpec = { kind: 'team', team: 'boat', free: false };
  readonly shelter: PinSpec = { kind: 'place', place: 'shelter' };
  readonly hospital: PinSpec = { kind: 'place', place: 'hospital' };
  readonly camp: PinSpec = { kind: 'place', place: 'camp' };
}
