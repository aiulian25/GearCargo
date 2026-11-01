import { describe, expect, it } from 'vitest'
import { translations } from '../i18n/translations'
import { displayPriceToPerLiter, displayVolumeToLiters, editedFuelTotal, fuelFormPayload,
  litersToDisplayVolume, pricePerLiterToDisplay, resolveFuelSystem, volumeUnitLabel,
  lPer100KmToMpg, kmToMiles, milesToKm } from '../utils/fuelEconomy'

describe('GC-015 explicit volume standards and lossless edit patches', () => {
  it.each([['gallons_us', 'us', 3.785411784], ['gallons_uk', 'uk', 4.54609]])('honors %s despite conflicting region', (volume_unit, system, factor) => {
    const user = { volume_unit, country_preference: system === 'us' ? 'GB' : 'US', currency: 'GBP' }
    expect(resolveFuelSystem({ volumeUnit: volume_unit, country: user.country_preference })).toBe(system)
    expect(displayVolumeToLiters(10, user)).toBeCloseTo(10 * factor, 10)
    expect(displayVolumeToLiters(litersToDisplayVolume(37.85, user), user)).toBeCloseTo(37.85, 12)
    expect(displayPriceToPerLiter(pricePerLiterToDisplay(-1.321, user), user)).toBeCloseTo(-1.321, 12)
    expect(lPer100KmToMpg(10 / 1.609344, system)).toBeCloseTo(10 * factor, 10)
    expect(volumeUnitLabel(user)).toBe(system === 'us' ? 'US gal' : 'imp gal')
  })
  it('retains the legacy regional interpretation without rewriting data', () => {
    expect(displayVolumeToLiters(1, { volume_unit: 'gallons', country_preference: 'US' })).toBe(3.785411784)
    expect(displayVolumeToLiters(1, { volume_unit: 'gallons', currency: 'GBP' })).toBe(4.54609)
    expect(kmToMiles(milesToKm(123456))).toBeCloseTo(123456, 10)
  })
  it.each(['liters', 'gallons_us', 'gallons_uk'])('omits unchanged rounded numbers on every notes save (%s)', volume_unit => {
    const user = { volume_unit }
    const original = { liters: 37.85, price_per_liter: 1.321, total_price: 49.99, odometer: 0 }
    const initial = { liters: litersToDisplayVolume(original.liters, user).toFixed(2),
      price_per_liter: pricePerLiterToDisplay(original.price_per_liter, user).toFixed(3),
      total_cost: original.total_price, mileage: 0, notes: 'Original', is_full_tank: true }
    for (let n = 0; n < 5; n++) {
      const data = { ...initial, liters: Number(initial.liters), mileage: '0', notes: `Edit ${n}` }
      expect(fuelFormPayload(data, user, initial)).toEqual({ notes: `Edit ${n}` })
      expect(editedFuelTotal(data, user, initial, original)).toBeNull()
    }
    const data = { ...initial, price_per_liter: '2.000' }
    expect(fuelFormPayload(data, user, initial)).toEqual({ price_per_liter: displayPriceToPerLiter(2, user) })
    expect(editedFuelTotal(data, user, initial, original)).toBe((37.85 * Number(displayPriceToPerLiter(2, user).toFixed(3))).toFixed(2))
  })
  it('keeps null, zero and signed quantities distinct', () => {
    const initial = { liters: '', price_per_liter: 0, total_cost: -10, mileage: '' }
    expect(fuelFormPayload({ ...initial, notes: 'Edited' }, {}, initial)).toEqual({ notes: 'Edited' })
    expect(fuelFormPayload({ ...initial, liters: '0', price_per_liter: '' }, {}, initial))
      .toEqual({ liters: 0, price_per_liter: null })
  })
  it('provides explicit unit labels and explanations in all supported languages', () => {
    for (const locale of Object.values(translations)) {
      for (const key of ['gallonsUs', 'gallonsUk', 'gallonsLegacy', 'unknown']) expect(typeof locale.units[key]).toBe('string')
      expect(locale.addFuel.pricePerUnit).toContain('{unit}')
      expect(typeof locale.vehicles.distanceUnitLocked).toBe('string')
      for (const key of ['sourceVolume', 'sourceDistance', 'sourceVolumeRequired', 'sourceDistanceRequired', 'sourceUnitsHint']) expect(typeof locale.backup[key]).toBe('string')
    }
  })
})
