import { ComponentFixture, TestBed } from '@angular/core/testing';
import { ActivatedRoute } from '@angular/router';
import { of } from 'rxjs';
import { ApiClientService } from '@rd/shared';
import { TeamConfirmComponent } from './team-confirm.component';

describe('TeamConfirmComponent', () => {
  let fixture: ComponentFixture<TeamConfirmComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TeamConfirmComponent],
      providers: [
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: {
              paramMap: { get: () => 'RES-BOAT-01' },
              queryParamMap: { get: (key: string) => (key === 'token' ? 'tm_demo' : null) },
            },
          },
        },
        {
          provide: ApiClientService,
          useValue: {
            getTeam: () => of({
              id: 'RES-BOAT-01',
              kind: 'boat',
              name: 'Motorized Rescue Boat',
              ward_id: 'ward_3',
              lat: 9.43,
              lng: 76.398,
              capacity_total: 12,
              capacity_remaining: 12,
              status: 'dispatched',
              simulated: true,
              location_source: 'simulated',
              assigned_request_id: 'req_demo',
            }),
            postTeamLocation: () => of({ id: 'RES-BOAT-01', status: 'dispatched' }),
            postTeamStatus: () => of({
              id: 'RES-BOAT-01',
              kind: 'boat',
              name: 'Motorized Rescue Boat',
              ward_id: 'ward_3',
              lat: 9.43,
              lng: 76.398,
              capacity_total: 12,
              capacity_remaining: 12,
              status: 'accepted',
            }),
          },
        },
      ],
    }).compileComponents();
    fixture = TestBed.createComponent(TeamConfirmComponent);
    fixture.detectChanges();
  });

  it('labels the open team link as a demo', () => {
    const note = fixture.nativeElement.querySelector('.demo') as HTMLElement;
    expect(note.textContent).toContain('Demo link');
    expect(note.textContent).toContain('not a signed-in coordinator screen');
  });

  it('offers Accepted while the team is dispatched and labels simulated movement', () => {
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Accepted');
    expect(text).toContain('Simulated movement');
    expect(text).toContain('req_demo');
  });

  it('shows permission denied when the browser blocks location', () => {
    spyOnProperty(navigator, 'geolocation', 'get').and.returnValue({
      watchPosition: (_ok: unknown, err: (error: { code: number }) => void) => {
        err({ code: 1 });
        return 4;
      },
      clearWatch: () => undefined,
      getCurrentPosition: () => undefined,
    } as Geolocation);
    (fixture.nativeElement.querySelector('button.share') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Location permission was denied');
    expect(fixture.componentInstance.sharing()).toBeFalse();
  });
});
