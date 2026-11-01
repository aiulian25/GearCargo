"""The explicit disclosure contract for bearer-link report JSON and PDFs.

Never pass users, vehicles or expense rows to the public PDF renderer. New
private report fields must not become public merely because a serializer grows.
"""
from dataclasses import dataclass
from types import MappingProxyType


from app.services.expense_ledger import CATEGORIES as SHARED_CATEGORIES, BASIS, BASIS_LABEL


@dataclass(frozen=True, slots=True)
class SharedVehicle:
    name: str
    make: str | None
    model: str | None


@dataclass(frozen=True, slots=True)
class SharedReport:
    basis_label: str
    as_of: str
    period_label: str
    start_date: str
    end_date: str
    vehicles: tuple[SharedVehicle, ...]
    entry_counts: MappingProxyType
    totals: MappingProxyType
    currency: str
    converted: bool
    fx_applied: bool
    label: str | None
    app_name: str
    expires_at: str | None

    @classmethod
    def from_summary(cls, summary, *, label, app_name, expires_at):
        return cls(
            basis_label=BASIS_LABEL, as_of=summary.get('as_of', summary['end_date']),
            period_label=summary['period_label'], start_date=summary['start_date'],
            end_date=summary['end_date'],
            vehicles=tuple(SharedVehicle(name=v['name'], make=v.get('make'), model=v.get('model'))
                           for v in summary['vehicles']),
            entry_counts=MappingProxyType({k: summary['entry_counts'][k]
                                          for k in (*SHARED_CATEGORIES, 'total')}),
            totals=MappingProxyType({k: summary['totals'][k]
                                    for k in (*SHARED_CATEGORIES, 'grand_total')}),
            currency=summary['currency'], converted=summary['converted'],
            fx_applied=summary['fx_applied'], label=label, app_name=app_name,
            expires_at=expires_at,
        )

    def to_dict(self):
        # Preserve the existing public JSON shape, with an explicit key list at
        # every level. Neither ORM identities nor row details cross this boundary.
        return {
            'basis': BASIS, 'basis_label': self.basis_label, 'as_of': self.as_of,
            'period_label': self.period_label, 'start_date': self.start_date,
            'end_date': self.end_date, 'vehicle_count': len(self.vehicles),
            'vehicles': [{'name': v.name, 'make': v.make, 'model': v.model} for v in self.vehicles],
            'entry_counts': {k: self.entry_counts[k] for k in (*SHARED_CATEGORIES, 'total')},
            'totals': {k: self.totals[k] for k in (*SHARED_CATEGORIES, 'grand_total')},
            'currency': self.currency, 'display_currency': self.currency,
            'converted': self.converted, 'fx_applied': self.fx_applied,
            'label': self.label, 'app_name': self.app_name, 'expires_at': self.expires_at,
        }
