---
name: mentor
description: Registrar y revisar la vida de Miguel en Mentor (plata, deudas y cuotas, peso, comidas, sueño, ánimo, súper) con las tools MCP mcp_mentor_*. Usar cuando Miguel cuente un gasto o ingreso, una deuda, un pago de cuota, lo que comió, su peso, cómo durmió, qué falta en casa, o pida un resumen, vencimientos o la revisión semanal.
version: 1.0.0
metadata:
  hermes:
    tags: [mentor, finanzas, salud, telegram]
    category: personal
---

# Mentor

Mentor es la app personal de Miguel. Todo lo que anotás acá aparece en la app al instante y al revés.
Las tools llegan por MCP con el prefijo `mcp_mentor_` (por ejemplo `mcp_mentor_add_transaction`).
Si no aparecen, corré `/reload-mcp` y, si siguen sin estar, avisale a Miguel que el servidor `mentor`
no responde. No inventes datos.

## Reglas

- Respondé en español rioplatense, corto, como en un chat. Plata en formato argentino: `$ 12.345,50`.
- **Solo hablás de esto en el chat privado con Miguel.** Si el mensaje viene de un grupo o de otra
  persona, no leas ni muestres datos de Mentor.
- **Anotá directo** cuando el mensaje es claro ("gasté 12500 en el súper"). Preguntá solo si falta algo
  que cambia el registro: monto, si es gasto o ingreso, a quién se le debe, cuántas cuotas.
- Después de cada alta, confirmá en una línea qué guardaste, con el id: "Anotado: gasto de $ 12.500 en
  Súper (#231)". Así se puede corregir.
- **Borrar o desmarcar** (`delete_transaction`, `set_installment_paid` con `paid=false`, rechazar un aviso
  de pago) solo con un "sí" explícito de Miguel después de mostrarle qué vas a tocar.
- Fechas en ISO (`YYYY-MM-DD`). "Ayer", "el viernes", etc. calculalos con el `today` que devuelve
  `get_overview`, no con tu reloj. Los rangos son `[from_date, to_date)`.
- Nunca muestres tokens, links de invitados ni el `MCP_TOKEN`.

## Qué tool usar

| Miguel dice | Tool |
|---|---|
| "Gasté 8.000 en nafta", "cobré el sueldo" | `add_transaction` (kind `expense`/`income`, categoría de la lista de la tool) |
| "Ana me debe 30 lucas en 3 cuotas" | `add_debt` (direction `owed_to_me`, kind `person`) |
| "Saqué un préstamo en Mercado Pago" | `add_debt` (kind `entity`, brand `mercadopago`, direction `i_owe`) |
| "Compré algo en 6 cuotas con la Naranja X" | `add_debt` (kind `card`, brand `naranjax`, `first_due` obligatorio) |
| "Le presté la tarjeta a Martín" | `lend_card` (crea las dos deudas enlazadas) |
| "Pagué la cuota de Brubank", "Ana me pagó" | `get_due_payments` o `get_debts` para encontrar el `installment_id`, después `set_installment_paid` |
| "¿Qué vence esta semana?" | `get_due_payments` (days 7) |
| "Dormí 6 horas", "ánimo 3", "caminé 40 min" | `save_checkin` (lo que no mandes queda como estaba) |
| "Almorcé milanesa con puré" | `log_food` |
| "Peso 81,4" / "mi meta es 78" | `log_weight` / `set_weight_goal` |
| "Falta yerba y pan" / "¿qué falta en casa?" | `add_to_home_list` / `get_home_list`; tachar con `toggle_home_item` |
| "¿Cómo vengo este mes?" | `get_overview`, y bajar a `list_transactions`, `get_debts`, etc. |
| "¿Cuánto subió la leche?" | `get_price_history` |
| "Ana avisó que pagó" | `get_overview` → `payment_claims_waiting_my_confirmation` → `resolve_payment_claim` |
| "Anoté mal ese gasto" | `list_transactions` para el id, confirmar, `delete_transaction` |

Marcas válidas: tarjetas `naranjax`, `mercadopago`, `brubank`, `lemon`, `visa`, `mastercard`, `amex`,
`cabal`. Entidades `mercadopago`, `naranjax`, `binance`, `brubank`, `lemon`, `uala`, `personalpay`,
`prex`, `cuentadni` y bancos (`galicia`, `santander`, `bbva`, `nacion`, `provincia`, `macro`, `icbc`,
`ciudad`, `supervielle`). Si no está, `brand` vacío y el nombre en `person`.

## Procedimientos

**Pago de cuota.** Buscá la cuota pendiente más próxima de esa deuda (la de menor `number` sin
`paid_on`). Si hay más de una deuda que coincide, preguntá cuál. Al marcarla, Mentor ya registra el
gasto o ingreso en Plata: no llames además a `add_transaction`.

**Resumen.** `get_overview` primero. Contestá con 3 a 5 líneas: balance del mes, lo que más gastó,
deudas que vencen en 7 días, y un dato de salud si hay algo raro (poco sueño, peso que sube).

**Revisión semanal.** Usá el prompt MCP `weekly_review` de Mentor si está disponible. Si no, seguí sus
pasos: overview, check-ins de 14 días, comidas de 7, movimientos del mes, deudas y peso de 90 días;
máximo 3 fallas concretas con su dato y una acción chica para cada una.

**Avisos programados.** Si Miguel pide recordatorios, creá un cron que entregue en Telegram. Por ejemplo:
`hermes cron create "daily at 9am" "Usá el skill mentor: llamá a get_due_payments con days 3 y, si hay
cuotas, mandame una línea por cada una con quién, monto, fecha y si está atrasada. Si no hay nada, no
mandes nada." --deliver telegram`.

## Errores comunes

- `add_debt` con kind `card` sin `first_due` o con una marca que no es de tarjeta falla: pedí la fecha
  del primer vencimiento del resumen.
- Tarjetas y entidades siempre son `i_owe`.
- Los montos van como número (`12500.5`), no como texto con puntos.
- Si una tool devuelve error, decí qué faltó en una línea y preguntá solo eso.
