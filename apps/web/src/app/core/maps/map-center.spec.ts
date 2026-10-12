import { centerMoved, panIfMoved } from './map-center';

describe('map centre', () => {
  it('pans when the selected alert moves the centre', () => {
    const map = { panTo: jasmine.createSpy('panTo') };
    let last = panIfMoved(map, null, { lat: 10.5, lng: 76.3 });
    expect(map.panTo).toHaveBeenCalledWith({ lat: 10.5, lng: 76.3 });
    last = panIfMoved(map, last, { lat: 10.2, lng: 76.1 });
    expect(map.panTo).toHaveBeenCalledTimes(2);
    expect(last).toEqual({ lat: 10.2, lng: 76.1 });
  });

  it('does not pan for the same centre or a bad value', () => {
    const map = { panTo: jasmine.createSpy('panTo') };
    panIfMoved(map, { lat: 1, lng: 2 }, { lat: 1, lng: 2 });
    panIfMoved(map, { lat: 1, lng: 2 }, { lat: NaN, lng: 2 });
    expect(map.panTo).not.toHaveBeenCalled();
    expect(centerMoved(null, undefined)).toBeFalse();
  });
});
