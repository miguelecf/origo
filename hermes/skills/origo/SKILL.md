---
name: origo
description: Registrar y revisar la vida del usuario en Origo (plata, suscripciones, deudas y cuotas, peso y composición, comidas, plan de dieta, rutina de entreno, sueño, ánimo, súper) con las tools MCP mcp_origo_*. Usar cuando el usuario cuente un gasto o ingreso, una suscripción, una deuda, un pago de cuota, lo que comió, su peso o lo que dio la balanza, un cambio en su plan de comidas o su rutina, cómo durmió, qué falta en casa, o pida un resumen, vencimientos o la revisión semanal.
version: 1.2.0
metadata:
  hermes:
    tags: [origo, finanzas, salud, telegram]
    category: personal
---

# Origo

Origo es la app personal del usuario: su registro de plata, deudas, cuerpo, entreno y súper. Todo lo que anotás acá aparece en la app al instante y al revés.
Las tools llegan por MCP con el prefijo `mcp_origo_` (por ejemplo `mcp_origo_add_transaction`).
Si no aparecen, corré `/reload-mcp` y, si siguen sin estar, avisale al usuario que el servidor `origo`
no responde. No inventes datos.

## Reglas

- Respondé en español rioplatense, corto, como en un chat. Plata en formato argentino: `$ 12.345,50`.
- **Solo hablás de esto en el chat privado con el usuario.** Si el mensaje viene de un grupo o de otra
  persona, no leas ni muestres datos de Origo.
- **Anotá directo** cuando el mensaje es claro ("gasté 12500 en el súper"). Preguntá solo si falta algo
  que cambia el registro: monto, si es gasto o ingreso, a quién se le debe, cuántas cuotas.
- Después de cada alta, confirmá en una línea qué guardaste, con el id: "Anotado: gasto de $ 12.500 en
  Súper (#231)". Así se puede corregir.
- **Borrar, vaciar o desmarcar** (`delete_transaction`, `delete_food_entry`, `clear_meal`,
  `copy_diet_day`, `delete_routine_item`, `delete_weight_milestone`, `set_installment_paid` con
  `paid=false`, rechazar un aviso de pago) solo con un "sí" explícito del
  usuario después de mostrarle qué vas a tocar.
- **El plan no es lo hecho.** Los objetivos de dieta no son comidas consumidas (eso es `log_food`), y
  cargar la rutina no marca entrenamientos: eso lo marca el usuario en la app. Nunca inventes un
  entrenamiento, una comida ni una medición.
- **Origo es la memoria; vos sos quien calcula.** Si el usuario te pide calorías o macros del plan,
  calculalos vos, decile de dónde salen y guardá el resultado con `set_diet_targets`. No son
  recomendaciones médicas: guardá lo que dice el plan del usuario, sin ajustarlo por tu cuenta.
- Fechas en ISO (`YYYY-MM-DD`). "Ayer", "el viernes", etc. calculalos con el `today` que devuelve
  `get_overview`, no con tu reloj. Los rangos son `[from_date, to_date)`.
- Nunca muestres tokens, links de invitados ni el `MCP_TOKEN`.

## Qué tool usar

| El usuario dice | Tool |
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
| "Peso 81,4" / "mi meta final es 78" | `log_weight` / `set_weight_goal` |
| "La balanza dio 35,8 % de grasa y 64 % de músculo" | `log_weight` con `fat_pct`, `muscle_pct` (y `lean_kg`, `water_pct`, `visceral_fat` si los dio). Solo lo que dijo: no estimes el resto |
| "Mi próximo objetivo es 105" | `add_weight_milestone`. **No** `set_weight_goal`: eso pisa la meta final |
| "¿Qué tengo que comer?" | `get_diet_plan` con `weekday` de hoy (`today_weekday`) |
| "El lunes y el jueves ceno tortilla" / "cambiá la merienda del martes" | `set_meal` (slot, una comida en un renglón, `weekdays`). Leé `format` en `get_diet_plan` |
| "Todos los días desayuno avena" | `set_meal` con `weekdays` [0,1,2,3,4,5,6] |
| "El sábado igual que el viernes" | `copy_diet_day` (pisa: confirmá antes) |
| "Sacá la media mañana del domingo" | `clear_meal` (confirmá antes) |
| "Anoté mal esa comida" | `get_food_log` para el id, confirmar, `delete_food_entry` |
| "Mi plan es 2200 kcal y 180 de proteína", "tomo creatina" | `set_diet_targets` (reglas y suplementos, uno por renglón) |
| "¿Qué entreno hoy?" / "agregá press banca 4×8–12 el lunes" | `get_routine` / `add_routine_item` (`reps` 8, `reps_max` 12) |
| "Subí la sentadilla a 62,5" | `get_routine` para el id, después `update_routine_item` |
| "¿Qué hice esta semana en el gym?" | `get_workout_history` |
| "Me suscribí a Claude, 20 dólares por mes" | `add_subscription` (currency `USD`, category `IA`, `next_charge` = fecha del próximo cobro) |
| "Se cobró Netflix", "me cobraron ChatGPT 26.000 pesos" | `get_subscriptions` para el id, después `mark_subscription_charged` (en USD, `amount_ars` obligatorio) |
| "¿Cuánto gasto en suscripciones?" | `get_subscriptions` (`monthly_cost` separa ARS y USD) |
| "Pausá Max" / "volví a Max" | `set_subscription_active` |
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
`paid_on`). Si hay más de una deuda que coincide, preguntá cuál. Al marcarla, Origo ya registra el
gasto o ingreso en Plata: no llames además a `add_transaction`.

**Resumen.** `get_overview` primero. Contestá con 3 a 5 líneas: balance del mes, lo que más gastó,
deudas que vencen en 7 días, y un dato de salud si hay algo raro (poco sueño, peso que sube).

**Revisión semanal.** Usá el prompt MCP `weekly_review` de Origo si está disponible. Si no, seguí sus
pasos: overview, check-ins de 14 días, comidas de 7, movimientos del mes, deudas y peso de 90 días;
máximo 3 fallas concretas con su dato y una acción chica para cada una.

**Rutina A/B.** La app tiene una rutina fija por día de la semana y no rota sola. Si el plan alterna
(A-B-A una semana, B-A-B la siguiente, con al menos un día de descanso entre entrenamientos), la
organizás vos: al empezar la semana, proponé qué día va cada rutina, esperá el "sí" y recién ahí
cambiá los días con las tools de rutina. Poné el nombre en el título del día (`set_routine_day_title`,
ej. "Rutina A"). No programes esto como automatización sin que el usuario lo pida.

**Cambios en el plan.** Antes de editar, leé (`get_diet_plan` o `get_routine`). Después de editar,
confirmá en una línea qué cambió. `set_meal` y `clear_meal` devuelven `previous` por día: si el
usuario dice "deshacé", volvé a guardar eso con `set_meal`.

**Formato de la dieta.** Una comida por momento y por día, en un solo renglón, con cantidades si el
plan las tiene: "200 g de pollo con arroz y ensalada". Nada de listas ni de "opción 1 / opción 2":
si el plan da opciones, preguntá cuál va cada día o repartilas vos y mostrá cómo quedó la semana.
El formato exacto está en `format`, en la respuesta de `get_diet_plan`.

**Límites de Origo.** Origo puede rechazar una escritura: fechas a futuro o muy viejas, montos sobre
el tope, un peso que se aleja mucho del último, demasiadas escrituras en una hora o una tool
deshabilitada. No es un error tuyo para esquivar: decile al usuario el motivo en una línea y, si
corresponde, que lo cargue desde la web. No reintentes con otros datos para pasar el límite.

**Si la web pide login.** El MCP y la web se autentican por separado: que la web pida contraseña en
un navegador no significa que el MCP esté caído. Decíselo así al usuario.

**Suscripciones.** Pesos y dólares no se suman entre sí: informalos por separado. Marcar un cobro ya lo
anota como gasto en Plata (categoría Suscripciones) y corre el próximo cobro; no llames además a
`add_transaction`. Si es en dólares y el usuario no dijo cuánto salió en pesos, preguntáselo.

**Avisos programados.** Si el usuario pide recordatorios, creá un cron que entregue en Telegram. Por ejemplo:
`hermes cron create "daily at 9am" "Usá el skill origo: llamá a get_due_payments con days 3 y a
get_overview; si hay cuotas o suscripciones (subscriptions.charging_next_7_days) por cobrarse, mandame
una línea por cada una con quién o qué, monto, fecha y si está atrasada. Si no hay nada, no
mandes nada." --deliver telegram`.

## Errores comunes

- `add_debt` con kind `card` sin `first_due` o con una marca que no es de tarjeta falla: pedí la fecha
  del primer vencimiento del resumen.
- Tarjetas y entidades siempre son `i_owe`.
- Los montos van como número (`12500.5`), no como texto con puntos.
- Si una tool devuelve error, decí qué faltó en una línea y preguntá solo eso.
