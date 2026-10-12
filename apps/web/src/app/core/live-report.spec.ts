import { announceReport, LIVE_REPORT } from './live-report';

describe('announceReport', () => {
  it('tells other tabs the new request id', () => {
    const posts: unknown[] = [];
    const Original = window.BroadcastChannel;
    (window as unknown as { BroadcastChannel: unknown }).BroadcastChannel = class {
      postMessage(msg: unknown): void {
        posts.push(msg);
      }
      close(): void {}
    };
    const openerPosts: unknown[] = [];
    spyOnProperty(window, 'opener', 'get').and.returnValue({
      closed: false,
      postMessage: (msg: unknown) => openerPosts.push(msg),
    });

    announceReport('rpt_1', 'req_phone');

    expect(posts).toEqual([{ type: LIVE_REPORT, reportId: 'rpt_1', requestId: 'req_phone' }]);
    expect(openerPosts).toEqual([{ type: LIVE_REPORT, reportId: 'rpt_1', requestId: 'req_phone' }]);
    window.BroadcastChannel = Original;
  });
});
