import { waitTipsFor } from './wait-tips';

describe('waitTipsFor', () => {
  it('maps each report type to three tips', () => {
    const rescue = ['status.tipHigh', 'status.tipWires', 'status.tipPhone'];
    expect(waitTipsFor('rescue')).toEqual(rescue);
    expect(waitTipsFor('flood')).toEqual(rescue);
    expect(waitTipsFor('medical')).toEqual(['status.tipMedical1', 'status.tipMedical2', 'status.tipMedical3']);
    expect(waitTipsFor('food')).toEqual(['status.tipFood1', 'status.tipFood2', 'status.tipFood3']);
    expect(waitTipsFor('food_water')).toEqual(waitTipsFor('food'));
    expect(waitTipsFor('shelter')).toEqual(['status.tipShelter1', 'status.tipShelter2', 'status.tipShelter3']);
    expect(waitTipsFor('animal_attack')).toEqual(['status.tipDog1', 'status.tipDog2', 'status.tipDog3']);
    expect(waitTipsFor('dog_attack')).toEqual(waitTipsFor('animal_attack'));
    expect(waitTipsFor('info')).toEqual(['status.tipDefault1', 'status.tipDefault2', 'status.tipDefault3']);
    expect(waitTipsFor(null)).toEqual(waitTipsFor('other'));
    for (const type of ['rescue', 'medical', 'food', 'shelter', 'animal_attack', 'other']) {
      expect(waitTipsFor(type).length).toBe(3);
    }
  });
});
