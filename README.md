# Piloto JEV

Piloto mínimo de **Jev** (TypeSafe AI), el modelo "System One" que en vez de
escribir texto devuelve decisiones tipadas: una opción, una nota o un sí/no,
cada una con su probabilidad.

Escrito siguiendo el [skill oficial de TypeSafe](https://github.com/typesafe-ai/skills)
y los docs en <https://docs.typesafe.ai>.

## Qué hay aquí

| Archivo | Qué es |
|---|---|
| `explicacion-jev.html` | La explicación *for dummies* en formato Zentauri. Ábrela primero. Trae una caja interactiva que corre en el navegador. |
| `piloto.py` | El piloto: triage de 5 tickets de soporte. Un archivo, sin dependencias. |

## Correr el piloto

```bash
python3 piloto.py                           # modo simulado, no necesita API key
export TYPESAFE_API_KEY=apikey_...          # contra el modelo real
python3 piloto.py
```

Sin API key usa un simulador de reglas de juguete que replica los campos reales
de la API, para ver la forma del dato sin gastar nada.

> **La API key nunca va en un archivo de este repo.** Solo como variable de
> entorno, y de preferencia en `~/.bashrc` o un gestor de secretos.

## La idea en tres líneas

1. Describes el **estado** (el ticket) y las **preguntas** (`choice`, `score`, `noul`).
2. Jev responde **tipado**, con probabilidades y confianza.
3. Tu código aplica reglas y ejecuta. Jev nunca toca nada.

## Las tres cosas que el skill corrigió

Son los errores que comete todo el mundo la primera vez:

**1. `confidence` es un campo propio — no es `max(probabilities)`.**
Mide cuánto sobresale la mejor opción por encima de un volado:

```
confidence = (p_max − 1/n) / (1 − 1/n)
```

Con 4 opciones, una probabilidad de 0.41 da una confianza de 0.21. Usar el 0.41
como "41% de seguridad" te hace actuar sobre casi un volado.

**2. `noul` devuelve un número de 0 a 1, no un booleano.**
Es la probabilidad del sí. El corte lo pones tú (`ES_REEMBOLSO = 0.80`).

**3. Un umbral global para todas las acciones es un anti-patrón.**
Van dos, por riesgo:

| Tramo | Qué pasa |
|---|---|
| `< 0.60` (`ESCALAR`) | nadie actúa solo, va a una persona |
| `0.60 – 0.85` | actúa si equivocarse es barato; confirma si no |
| `> 0.85` (`RIESGO_ALTO`) | ejecuta, incluso lo que mueve dinero |

## Lo que apareció al probar contra el modelo real

**Las probabilidades de un `score` vienen indexadas por posición, no por nombre.**
Vuelven como `{"0": 0.0, "1": 0.30, "2": 0.56, "3": 0.14}`, y el nombre de cada
nivel lo da `legend` (que trae los cuatro, no solo los extremos). Si lees
`probabilities["Urgente"]` te explota.

**La confianza colapsa a 1.00 en los casos fáciles.** Los cinco tickets de
ejemplo dan 1.00 porque las probabilidades salen degeneradas (0.0 / 1.0). Para
ver el tramo de escalamiento hace falta un caso genuinamente mixto — el ticket 6
habla de un cargo *y* de un fallo técnico, y da confianza 0.48. Un piloto en el
que la revisión humana nunca se dispara no demuestra nada.

**Coste observado:** ~530 input / ~88 output tokens por ticket, con las tres
preguntas en una sola llamada.

## Limitaciones conocidas de jev-1.13

Del *model jaggedness* oficial, lo que afecta a este piloto:

- **Lee literal** — los `criteria` describen condiciones explícitas, no etiquetas sueltas.
- **Sesgo de orden** — se inclina por la primera opción; reordena y verifica.
- **No cuenta** — nada de aritmética ni comparar fechas; eso va en código.
- **Se distrae** — filtra el `state` antes de preguntar.
- **No desconfía del `state`** — le entran instrucciones inyectadas.

## Para adaptarlo a un caso tuyo

Cambia el diccionario `PREGUNTAS` y las reglas de `decidir()`. El resto del
archivo no se toca.

## Antes de producción

Los umbrales de este piloto están puestos a dedo. Etiqueta ~50 casos a mano,
mide, y ajústalos con la matriz de costos real (qué cuesta un falso positivo
contra un falso negativo).

## Referencias

- Docs: <https://docs.typesafe.ai> · índice para agentes: <https://docs.typesafe.ai/llms.txt>
- Confianza vs. probabilidad: <https://docs.typesafe.ai/confidence.md>
- Routing por confianza: <https://docs.typesafe.ai/patterns/confidence-routing.md>
- Limitaciones de jev-1.13: <https://docs.typesafe.ai/model-jaggedness/jev-1.13.md>
- Casos de uso: <https://jevai.dev/es/user-cases/>
