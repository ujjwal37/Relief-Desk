import { ComponentFixture, TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { ActivatedRoute } from '@angular/router';
import { StatusComponent } from './status.component';
import { ApiClientService, ReportStatusResponse } from '@rd/shared';

describe('StatusComponent', () => {
  let component: StatusComponent;
  let fixture: ComponentFixture<StatusComponent>;
  let apiSpy: jasmine.SpyObj<ApiClientService>;

  const mockStatus: ReportStatusResponse = {
    report_id: 'R-0412',
    request_id: 'REQ-0412',
    status: 'on_the_way',
    hero_title: 'Sent. Help is being arranged.',
    hero_subtitle: 'Request R-0412 · 11:42 · you can close the app',
    eta_minutes: 18,
    eta_display: '~18 min',
    delivery_status: 'In progress',
    timeline: [
      {
        step: 1,
        name: 'received',
        title: 'Received / प्राप्त',
        state: 'done',
        timestamp: '11:42',
        description: 'Request R-0412 saved',
      },
      {
        step: 2,
        name: 'matched',
        title: 'Matched / मिलान हुआ',
        state: 'done',
        timestamp: '11:44',
        description: 'Volunteer boat team assigned',
      },
      {
        step: 3,
        name: 'on_the_way',
        title: 'On the way / सहायता रवाना',
        state: 'current',
        timestamp: '11:48',
        description: 'Boat B-03 · from Ward 6 jetty',
      },
      {
        step: 4,
        name: 'fulfilled',
        title: 'Fulfilled / सहायता पहुँची',
        state: 'pending',
        timestamp: null,
        description: 'You can confirm when help arrives',
      },
    ],
    while_you_wait_tips: [
      'Move to the highest safe place.',
      'Stay away from flood water and live wires.',
      'Keep your phone charged and stay reachable.',
    ],
    emergency_phone: '112',
    synthetic: true,
  };

  beforeEach(async () => {
    apiSpy = jasmine.createSpyObj('ApiClientService', ['getReportStatus']);
    apiSpy.getReportStatus.and.returnValue(of(mockStatus));

    await TestBed.configureTestingModule({
      imports: [StatusComponent],
      providers: [
        { provide: ApiClientService, useValue: apiSpy },
        {
          provide: ActivatedRoute,
          useValue: {
            snapshot: { queryParams: { id: 'R-0412', token: 'tok_demo' } },
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(StatusComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  afterEach(() => fixture.destroy());

  it('keeps watching until the request is finished', () => {
    expect(component.stillWaiting('new')).toBeTrue();
    expect(component.stillWaiting('dispatched')).toBeTrue();
    expect(component.stillWaiting('completed')).toBeFalse();
    expect(component.stillWaiting('resolved')).toBeFalse();
  });

  it('should create and load initial status', () => {
    expect(component).toBeTruthy();
    expect(component.statusData()?.report_id).toBe('R-0412');
    expect(component.statusData()?.eta_display).toBe('~18 min');
  });

  it('should render 4 timeline steps matching mockup', () => {
    const timeline = component.statusData()?.timeline;
    expect(timeline?.length).toBe(4);
    expect(timeline?.[0].state).toBe('done');
    expect(timeline?.[2].state).toBe('current');
  });

  it('should trigger fetchStatus on track submit', () => {
    component.reportIdInput.set('REQ-999');
    component.tokenInput.set('tok-999');
    component.onTrackSubmit();
    expect(apiSpy.getReportStatus).toHaveBeenCalledWith('REQ-999', 'tok-999');
  });
});
