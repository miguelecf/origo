"""Prueba visual y funcional aislada. Ejecutar con uv run --with playwright python scripts/verify_product_ui.py --shots /tmp/shots.
No usa mentor.db ni el servidor de desarrollo; un solo Chromium, puerto temporal.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from decimal import Decimal
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def seed():
    from app.core.clock import today
    from app.core.database import SessionLocal, init_db
    from app.services import body, checkins, debts, finance, guests, lists

    init_db()
    with SessionLocal() as db:
        finance.add_transaction(db, kind="income", amount=Decimal(1850000), category="Sueldo")
        finance.add_transaction(db, kind="expense", amount=Decimal(480000), category="Casa", note="Alquiler")
        finance.add_transaction(db, kind="expense", amount=Decimal(85000), category="Transporte", note="Nafta")
        debts.create_debt(db, person="Ana", direction="owed_to_me", total=Decimal(90000), installments=3,
                          first_due=today() + dt.timedelta(days=2), description="Entradas y cena")
        debts.create_debt(db, person="Visa Galicia", direction="i_owe", kind="card", brand="visa",
                          total=Decimal(360000), installments=6, first_due=today() + dt.timedelta(days=4), description="La heladera")
        debts.create_debt(db, person="", direction="i_owe", kind="entity", brand="mercadopago",
                          total=Decimal(75000), installments=3, first_due=today() + dt.timedelta(days=6))
        debts.create_debt(db, person="Marcos", direction="i_owe", total=Decimal(18000), description="La cena del sábado")
        for days, weight in [(28, "86.2"), (21, "85.8"), (14, "85.5"), (7, "85.3"), (0, "85.0")]:
            body.log_weight(db, Decimal(weight), today() - dt.timedelta(days=days))
        body.set_goal(db, Decimal(80))
        body.log_food(db, "Tostadas con queso y café con leche")
        body.log_food(db, "Milanesa con ensalada")
        for days in range(1, 5):
            checkins.save_checkin(db, today() - dt.timedelta(days=days), sleep_hours=Decimal("7.5"), mood=4, movement_min=35)
        lists.add_home_items(db, "Leche, Pan integral, Yerba, Manzanas")
        trip = lists.start_trip(db)
        lists.save_trip(db, trip.id, [
            {"name": "Leche", "price": "1850", "qty": "2"},
            {"name": "Pan integral", "price": "3200", "qty": "1"},
            {"name": "Yerba", "price": "5100", "qty": "1"},
            {"name": "Manzanas", "price": "2300", "qty": "1.5"},
        ], budget="25000")
        _, token = guests.create_guest(db, name="Ana", can_lists=True, can_debts=True)
        return token


def verify(base, shots, token):
    from playwright.sync_api import expect, sync_playwright
    from sqlalchemy import select
    from app.core.database import SessionLocal
    from app.models import Debt, Transaction

    errors, captures, overflows = [], [], []
    executable = Path.home() / "Library/Caches/ms-playwright/chromium_headless_shell-1243/chrome-headless-shell-mac-arm64/chrome-headless-shell"
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(executable), headless=True)
        for width in (390, 1280):
            for theme in ("light", "dark"):
                context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=theme)
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
                def capture(name):
                    page.wait_for_timeout(300)
                    path = shots / f"{name}-{width}-{theme}.png"
                    page.screenshot(path=str(path), full_page=True)
                    captures.append(path.name)
                    bad = page.evaluate("""() => [...document.querySelectorAll('body *')].filter(el => {
                      const r = el.getBoundingClientRect(); return r.width && (r.right > innerWidth + 1 || r.left < -1);
                    }).map(el => ({tag: el.tagName, class: el.className, text: el.textContent.slice(0, 60)}))""")
                    if page.evaluate("document.documentElement.scrollWidth > innerWidth"):
                        overflows.append({"capture": path.name, "elements": bad})
                for name, route in [("inicio", "/"), ("plata", "/plata"), ("deudas", "/deudas"),
                                    ("super", "/super"), ("compra", "/super/compra"),
                                    ("cuerpo", "/cuerpo"), ("dia", "/dia"), ("invitados", "/invitados")]:
                    page.goto(base + route, wait_until="networkidle")
                    capture(name)
                page.goto(base + "/deudas", wait_until="networkidle")
                page.locator(".debt-form > summary").click()
                page.locator('label:has(input[name="kind"][value="entity"])').click()
                capture("deudas-entidad")
                page.locator('label:has(input[name="kind"][value="card"])').click()
                capture("deudas-tarjeta")
                page.goto(base + "/g/" + token, wait_until="networkidle")
                page.goto(base + "/deudas", wait_until="networkidle")
                capture("invitado")
                page.goto(base + "/super/compra", wait_until="networkidle")
                capture("empezar-compra")
                context.close()

        # Escritura real, cursor, selección, pegado y lectura de Alpine.
        context = browser.new_context(viewport={"width": 390, "height": 900})
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(base + "/plata", wait_until="networkidle")
        amount = page.locator('[name="amount"]')
        amount.press_sequentially("1234567,5")
        assert amount.input_value() == "1.234.567,5"
        assert amount.evaluate("el => el.selectionStart") == 11
        amount.evaluate("el => el.setSelectionRange(5, 5)")
        amount.press("9")
        assert amount.input_value() == "12.349.567,5"
        assert amount.evaluate("el => el.selectionStart") == 6
        amount.fill("1234567,5")
        page.locator('[name="note"]').fill("Prueba de formato")
        page.get_by_role("button", name="Guardar gasto").click()
        expect(page.locator('.lines').get_by_text('Prueba de formato', exact=False)).to_be_visible()
        page.wait_for_load_state("networkidle")
        with SessionLocal() as db:
            tx = db.scalar(select(Transaction).where(Transaction.note == "Prueba de formato"))
            assert tx.amount == Decimal("1234567.50")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.goto(base + "/deudas", wait_until="networkidle")
        page.locator(".debt-form > summary").click()
        page.locator('label:has(input[name="kind"][value="card"])').click()
        page.locator('[name="person"]').fill("Visa prueba")
        page.locator('[name="total"]').press_sequentially("1234567,5")
        page.locator('[name="first_due"]').fill("2027-01-10")
        page.get_by_role("button", name="Guardar deuda", exact=True).click()
        expect(page.locator('.debt').get_by_text('Visa prueba', exact=True)).to_be_visible()
        page.wait_for_load_state("networkidle")
        with SessionLocal() as db:
            debt = db.scalar(select(Debt).where(Debt.person == "Visa prueba"))
            assert debt is not None, (page.url, page.locator('main').inner_text())
            assert debt.total == Decimal("1234567.50") and debt.kind == "card" and debt.brand == "visa"
        page.goto(base + "/super/compra", wait_until="networkidle")
        price = page.locator('[x-model="draft.price"]')
        price.press_sequentially("1234567,5")
        assert price.input_value() == "1.234.567,5"
        assert page.locator('[x-data]').evaluate("el => Alpine.$data(el).draft.price") == "1.234.567,5"
        page.locator('[x-model="draft.name"]').fill("Prueba")
        page.get_by_role("button", name="Sumar", exact=True).click()
        page.wait_for_timeout(900)
        assert page.locator('[x-data]').evaluate("el => Alpine.$data(el).total") == 1250017.5
        budget = page.locator('[x-model="budget"]')
        budget.fill("2345678,9")
        assert budget.input_value() == "2.345.678,9"
        ticket_price = page.locator('input.p').first
        ticket_price.fill("1234567,5")
        with page.expect_response(lambda r: r.request.method == "PUT") as response:
            ticket_price.press("Tab")
        assert response.value.ok
        assert Decimal(response.value.json()["total"]) == Decimal("1250017.50")
        page.reload(wait_until="networkidle")
        assert page.locator('input.p').first.input_value() == "1.234.567,5"
        assert page.locator('[x-model="budget"]').input_value() == "2.345.678,9"
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.screenshot(path=str(shots / "monto-grande-390.png"), full_page=True)
        # Separadores, borrado y pegado en medio, sin salto al final.
        price = page.locator('[x-model="draft.price"]')
        price.fill("1234")
        price.evaluate("el => el.setSelectionRange(2, 2)")
        price.press("Backspace")
        assert price.input_value() == "234" and price.evaluate("el => el.selectionStart") == 0
        price.fill("1234567,50")
        price.evaluate("el => el.setSelectionRange(2, 5)")
        price.press("8")
        assert price.input_value() == "18.567,50" and price.evaluate("el => el.selectionStart") == 2
        # Navegación HTMX + Alpine funciona después de cambiar de sección.
        page.get_by_role("link", name="Deudas", exact=True).click()
        page.wait_for_load_state("networkidle")
        page.locator(".debt-form > summary").click()
        page.locator('label:has(input[name="kind"][value="entity"])').click()
        expect(page.get_by_text("Elegí la entidad", exact=True)).to_be_visible()
        context.close()
        browser.close()
    result = {"captures": captures, "console_errors": errors, "horizontal_overflows": overflows,
              "money_tests": "passed: typing, caret, paste, selection, server, Alpine, ticket, budget, reload"}
    (shots / "results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    assert not errors, errors
    assert not overflows, overflows
    print(json.dumps({"captures": len(captures) + 1, "console_errors": len(errors), "overflows": len(overflows), "money": "passed"}))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--shots", type=Path, required=True)
    args = parser.parse_args()
    args.shots.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mentor-product-") as temporary:
        os.environ.update(DATABASE_URL=f"sqlite:///{temporary}/test.db", APP_PASSWORD="", GITHUB_CLIENT_ID="")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        token = seed()
        with (args.shots / "server.log").open("w") as log:
            process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        with urlopen(base, timeout=1):
                            break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError("El servidor temporal no inició")
                verify(base, args.shots, token)
            finally:
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
