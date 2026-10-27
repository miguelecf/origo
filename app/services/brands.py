"""Tarjetas y entidades con logo propio (los archivos están en static/brands/<slug>.png)."""

# Primero las que usa el dueño.
CARDS = {
    "naranjax": "Naranja X",
    "mercadopago": "Mercado Pago",
    "brubank": "Brubank",
    "lemon": "Lemon",
    "visa": "Visa",
    "mastercard": "Mastercard",
    "amex": "American Express",
    "cabal": "Cabal",
}

ENTITIES = {
    "mercadopago": "Mercado Pago",
    "naranjax": "Naranja X",
    "binance": "Binance",
    "brubank": "Brubank",
    "lemon": "Lemon",
    "uala": "Ualá",
    "personalpay": "Personal Pay",
    "prex": "Prex",
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
