"""Tarjetas y entidades con logo propio (los archivos están en static/brands/<slug>.png)."""

CARDS = {
    "visa": "Visa",
    "mastercard": "Mastercard",
    "amex": "American Express",
    "naranjax": "Naranja X",
    "cabal": "Cabal",
}

ENTITIES = {
    "mercadopago": "Mercado Pago",
    "naranjax": "Naranja X",
    "uala": "Ualá",
    "brubank": "Brubank",
    "personalpay": "Personal Pay",
    "prex": "Prex",
    "lemon": "Lemon",
    "cuentadni": "Cuenta DNI",
    "galicia": "Galicia",
    "santander": "Santander",
    "bbva": "BBVA",
    "nacion": "Banco Nación",
    "provincia": "Banco Provincia",
    "macro": "Macro",
    "icbc": "ICBC",
    "ciudad": "Banco Ciudad",
    "supervielle": "Supervielle",
}

CATALOGS = {"card": CARDS, "entity": ENTITIES}


def label(slug: str | None) -> str:
    return CARDS.get(slug or "") or ENTITIES.get(slug or "") or ""
