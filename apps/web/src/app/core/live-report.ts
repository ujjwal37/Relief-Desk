/** Tell every open Relief Desk tab that a citizen report was saved. */
export const LIVE_REPORT = 'rd-report-submitted';
export const LIVE_CHANNEL = 'rd-live';

export interface LiveReportMessage {
  type: typeof LIVE_REPORT;
  reportId: string;
  requestId?: string;
}

export function announceReport(reportId: string, requestId?: string): void {
  const msg: LiveReportMessage = { type: LIVE_REPORT, reportId, requestId };
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage(msg, window.location.origin);
    }
  } catch {
    // A cross-origin parent cannot be notified.
  }
  try {
    const opener = window.opener as { closed?: boolean; postMessage?: (data: unknown, origin: string) => void } | null;
    if (opener && !opener.closed) {
      opener.postMessage?.(msg, window.location.origin);
    }
  } catch {
    // The opener tab is already gone.
  }
  try {
    const channel = new BroadcastChannel(LIVE_CHANNEL);
    channel.postMessage(msg);
    channel.close();
  } catch {
    // BroadcastChannel is missing in this browser.
  }
}
