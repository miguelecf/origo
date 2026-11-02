"""Los catálogos conservan sus datos sin distribuir logos de terceros."""
from decimal import Decimal
from pathlib import Path

from app.core.clock import today
from app.services import brands, debts

ROOT = Path(__file__).resolve().parents[1]


def test_brand_picker_uses_named_neutral_initials(client):
    page = client.get("/deudas").text
    assert "/static/brands/" not in page
    for catalog in brands.CATALOGS.values():
        for slug, name in catalog.items():
            assert f'value="{slug}"' in page
            assert f'aria-hidden="true">{name[:2].upper()}</span><span>{name}</span>' in page
            assert brands.label(slug) == name
    assert not list((ROOT / "app/static/brands").glob("*.png"))


def test_existing_brand_debt_keeps_slug_and_custom_name(client, db):
    debt = debts.create_debt(
        db, person="Visa Galicia", kind="card", brand="visa", direction="i_owe",
        total=Decimal("120.00"), installments=2, first_due=today(),
    )
    page = client.get("/deudas").text
    assert "/static/brands/" not in page
    assert '<span class="avatar initials" aria-hidden="true">VI</span>' in page
    assert "<b>Visa Galicia</b>" in page
    db.refresh(debt)
    assert debt.brand == "visa" and debt.person == "Visa Galicia"
    assert debt.total == Decimal("120.00") and len(debt.installments) == 2
