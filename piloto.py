#!/usr/bin/env python3
"""
Piloto JEV — triage de tickets de soporte.

La idea en una frase: en vez de pedirle a un LLM que escriba un texto y luego
tratar de adivinar qué quiso decir, le hacemos preguntas cerradas y nos
devuelve respuestas tipadas que el código puede usar directo.

Jev opina. Este archivo decide y ejecuta. Esa separación es el punto.

Escrito siguiendo el skill oficial de TypeSafe (docs.typesafe.ai). Las tres
decisiones de diseño que vienen de ahí están marcadas con [skill].

Uso:
    python3 piloto.py            # modo simulado, no necesita API key
    TYPESAFE_API_KEY=apikey_... python3 piloto.py
"""

import json
import os
import urllib.error
import urllib.request

API_URL = "https://api.typesafe.ai/v1/systemone"
MODELO = "jev-1.13.0"  # versión fijada: con jev-latest el comportamiento cambia bajo tus pies


# ---------------------------------------------------------------- 1. LAS PREGUNTAS
# Los tres tipos de pregunta que entiende Jev. Esto es todo el "prompt" que hay.
#
# [skill] jev-1.13 lee literal: responde la pregunta que escribiste, no la que
# querías. Por eso los criterios describen condiciones explícitas, no etiquetas
# sueltas. Y jev-1.13 se inclina por la primera opción de la lista, así que si
# cambias el orden conviene verificar que la respuesta no se mueva.
PREGUNTAS = {
    # choice -> elige UNA opción de un menú cerrado
    "equipo": {
        "type": "choice",
        "instructions": "¿Qué equipo debe atender este ticket?",
        "criteria": {
            "facturacion": "Cobros, pagos, facturas, reembolsos",
            "tecnico": "Errores, caídas, integraciones que fallan, lentitud",
            "ventas": "Precios, planes, quiere comprar o ampliar",
            "otro": "Saludos, agradecimientos, o nada de lo anterior",
        },
    },
    # score -> califica contra una escala ordenada (de menos a más)
    "urgencia": {
        "type": "score",
        "instructions": "¿Qué tan urgente es responder este ticket?",
        "criteria": [
            "Puede esperar días",
            "Normal, dentro del día",
            "Urgente, en horas",
            "Crítico, el cliente está bloqueado ahora",
        ],
    },
    # noul -> sí/no, devuelve la PROBABILIDAD de que sea sí (0 a 1)
    "pide_reembolso": {
        "type": "noul",
        "instructions": "¿El cliente pide explícitamente que le devuelvan dinero?",
        "criteria": {
            "true": "Pide reembolso, devolución, o reversar un cobro ya hecho",
            "false": "No menciona devolución de dinero",
        },
    },
}


# ---------------------------------------------------------------- 2. LA LLAMADA
def preguntar_a_jev(texto: str) -> dict:
    """Manda el estado + las tres preguntas en UNA llamada, devuelve `answers`.

    [skill] Las preguntas son independientes entre sí, así que van juntas en el
    mismo request: un solo viaje, un solo cobro.
    """
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        return simular(texto)

    cuerpo = json.dumps(
        {"model": MODELO, "state": {"ticket": texto}, "questions": PREGUNTAS}
    ).encode()

    pedido = urllib.request.Request(
        API_URL,
        data=cuerpo,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(pedido, timeout=30) as r:
            return json.load(r)["answers"]
    except urllib.error.HTTPError as e:
        print(f"  [la API respondió {e.code}: {e.read().decode()[:200]}]")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"  [no se pudo llamar a la API: {e}]")
    return simular(texto)


# ---------------------------------------------------------------- 3. LA DECISIÓN
# Aquí no hay IA. Son reglas nuestras, legibles y auditables, sobre datos tipados.
#
# [skill] Un solo umbral global para todo es un anti-patrón explícito en los
# docs. La confianza es el segundo eje: la respuesta dice QUÉ, la confianza dice
# SI ACTUAR. Y el umbral depende de lo que cueste equivocarse.
ESCALAR = 0.60       # debajo de esto nadie actúa solo, sin importar la acción
RIESGO_ALTO = 0.85   # mínimo para ejecutar sin preguntar algo que mueve plata
ES_REEMBOLSO = 0.80  # noul es una probabilidad: hay que ponerle un corte


def decidir(r: dict) -> str:
    equipo = r["equipo"]["choice"]
    conf = r["equipo"]["confidence"]       # campo propio, NO max(probabilities)
    urgencia = r["urgencia"]["score"]
    p_reembolso = r["pide_reembolso"]["noul"]  # número de 0 a 1, no booleano

    # Tramo 1 — el modelo duda: no adivinamos.
    if conf < ESCALAR:
        return f"revisión humana (confianza {conf:.2f} < {ESCALAR})"

    # Tramo 2 — toca dinero: alto riesgo, exige más confianza.
    if p_reembolso >= ES_REEMBOLSO:
        if conf >= RIESGO_ALTO:
            return "cola de reembolsos — automático"
        return "cola de reembolsos — pide confirmación a un agente"

    # Tramo 3 — solo enruta: bajo riesgo, basta con haber pasado ESCALAR.
    if urgencia >= 2.5:
        return f"{equipo} — atención inmediata"
    return f"{equipo} — cola normal"


# ---------------------------------------------------------------- 4. EL SIMULADOR
# Reglas de juguete para que el piloto corra sin API key y se vea la forma del
# dato. Replica los campos reales de la API, incluida la fórmula de confianza:
#     confidence = (p_max - 1/n) / (1 - 1/n)
def confianza(probs: dict) -> float:
    n = len(probs)
    return (max(probs.values()) - 1 / n) / (1 - 1 / n)


def simular(texto: str) -> dict:
    t = texto.lower()

    def tiene(*palabras):
        return any(p in t for p in palabras)

    if tiene("cobr", "factur", "pag", "devu", "reembols"):
        probs = {"facturacion": 0.91, "tecnico": 0.04, "ventas": 0.03, "otro": 0.02}
    elif tiene("error", "falla", "no funciona", "caíd", "lent", "500"):
        probs = {"tecnico": 0.89, "facturacion": 0.05, "ventas": 0.04, "otro": 0.02}
    elif tiene("precio", "plan", "cotiz", "contratar"):
        probs = {"ventas": 0.88, "facturacion": 0.06, "tecnico": 0.03, "otro": 0.03}
    else:
        probs = {"otro": 0.41, "tecnico": 0.27, "facturacion": 0.19, "ventas": 0.13}

    niveles = PREGUNTAS["urgencia"]["criteria"]
    alto = tiene("urgente", "ya", "inmediat", "perdiendo", "caíd", "bloquead")
    # Ojo: la API indexa estas probabilidades por POSICIÓN ("0".."3"), no por
    # el nombre del nivel. El nombre se resuelve con `legend`.
    p_urg = (
        {"0": 0.00, "1": 0.07, "2": 0.56, "3": 0.37}
        if alto
        else {"0": 0.18, "1": 0.64, "2": 0.18, "3": 0.00}
    )

    return {
        "equipo": {
            "type": "choice",
            "choice": max(probs, key=probs.get),
            "probabilities": probs,
            "confidence": confianza(probs),
        },
        "urgencia": {
            "type": "score",
            "score": sum(i * p for i, p in enumerate(p_urg.values())),
            "legend": {str(i): n for i, n in enumerate(niveles)},
            "probabilities": p_urg,
            "confidence": confianza(p_urg),
        },
        "pide_reembolso": {
            "type": "noul",
            "noul": 0.93 if tiene("devu", "reembols", "reversar") else 0.04,
        },
    }


# ---------------------------------------------------------------- MAIN
TICKETS = [
    "Me cobraron dos veces el plan de septiembre. Devuélvanme uno, por favor.",
    "La integración con el ERP tira error 500 desde ayer y estamos perdiendo pedidos.",
    "Buenas, ¿cuánto cuesta el plan para 50 usuarios?",
    "Hola, quería saludar y felicitarlos por el producto.",
    "El dashboard carga lentísimo, es urgente, no podemos cerrar el mes.",
    # Mixto a propósito: habla de un cargo Y de un fallo técnico. Es el caso
    # que dispara el tramo de escalamiento — sin él el piloto no demuestra
    # su función más importante.
    "Hola, tengo una duda sobre el cargo del mes pasado y también no me carga el panel.",
]


def nivel(r: dict) -> str:
    """Nombre del nivel de urgencia, leído del `legend` que devuelve la API."""
    leyenda = r["urgencia"].get("legend") or {}
    return leyenda.get(str(round(r["urgencia"]["score"])), "—")


def main():
    modo = "API real" if os.environ.get("TYPESAFE_API_KEY") else "SIMULADO (sin API key)"
    print(f"\nPiloto JEV · triage de tickets · modo: {modo}\n" + "─" * 74)

    for i, ticket in enumerate(TICKETS, 1):
        r = preguntar_a_jev(ticket)
        print(f"\n{i}. {ticket}")
        print(
            f"   equipo         = {r['equipo']['choice']:<12}"
            f" confianza {r['equipo']['confidence']:.2f}"
        )
        print(f"   urgencia       = {r['urgencia']['score']:.2f}  ({nivel(r)})")
        print(f"   pide_reembolso = {r['pide_reembolso']['noul']:.2f}  (probabilidad)")
        print(f"   → acción: {decidir(r)}")

    print("\n" + "─" * 74)
    print("Jev respondió las 3 preguntas. `decidir()` tomó la acción. Nada de texto libre.\n")


if __name__ == "__main__":
    main()
