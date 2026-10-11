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
          useValue: { snapshot: { paramMap: { get: () => 'RES-BOAT-01' } } },
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
              status: 'available',
              simulated: true,
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
});
