# Calendar dates, instants and display preferences

GearCargo keeps calendar dates and instants separate. This is a presentation/API
correction; it does not migrate or shift stored records.

- **Calendar dates** use `YYYY-MM-DD`: expense dates, insurance coverage, document
  expiry, due dates, and period keys. Construct and group these values without
  converting local midnight to UTC. The expense ledger owns year/month grouping;
  the frontend keeps its date and month keys unchanged.
- **Input defaults** use the device's current local calendar day, including near
  midnight and during daylight saving time. Insurance's one-year default clamps
  February 29 to February 28 in a non-leap year. A saved account timezone affects
  instant display, not the literal day chosen in a date input.
- **Instants** such as creation, completion, backup, sync, and session timestamps
  are stored as naive UTC in existing database columns. API serializers use
  `isoformat_utc` to add `Z`; explicitly offset values are normalized to UTC.
  `None` remains JSON null. Date columns never go through this serializer.
- **Legacy API/cache timestamps** containing a date and time but no offset mean
  UTC. The frontend adds `Z` before parsing those values. Explicit offsets retain
  their meaning. No stored timestamp is reinterpreted or rewritten. Parking
  start/end clock fields are wall times paired with an entry date and retain their
  existing contract; they must not be treated as UTC creation timestamps. Portable
  backup storage fields and internal job metadata retain their existing formats.
- **Presentation** uses `useDateFormat` inside `UserPreferencesSync`'s reactive
  `DateFormatProvider`. Language changes and loaded/updated profiles update date
  names immediately. User `date_format` controls numeric dates (`DD/MM/YYYY`,
  `MM/DD/YYYY`, `YYYY-MM-DD`, or `DD.MM.YYYY`); an absent or unsupported format uses
  the established `DD/MM/YYYY` default. Named styles and chart months use EN/RO/ES
  locale data from `Intl`, so no duplicate month translation table is needed.
- **Display timezone** is the saved account `timezone` for instants. Before sign-in
  or without a saved timezone it uses the browser zone; invalid legacy timezone
  preferences fall back to UTC. Calendar dates render identically in every zone.
  Date-only values passed to the datetime formatter stay dates: no midnight is
  invented. Malformed dates render `-` rather than rolling into another month.

Use the pure helpers in `frontend/src/utils/dateFormat.js` outside React and pass
preferences explicitly. Do not parse formatted display text back into stored dates
or numbers. Numeric/currency parsing is unchanged.

Historical entries that were saved on the wrong date need owner confirmation of
intent before correction. This change cannot infer that intent from a stored day.
