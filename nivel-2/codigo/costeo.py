"""Costo de ingredientes por porción al 31/10/2026 — El Término Medio, nivel 2.

Uso (desde la raíz del repo):
    python nivel-2/codigo/costeo.py

Lee los insumos de nivel-2/ y escribe nivel-2/costos.csv.
Requiere `pdftotext` (Poppler) en el PATH para leer los PDF.
"""

import csv
import json
import re
import subprocess
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # carpeta nivel-2/
FECHA_COSTEO = "2026-10-31"
TOL_NETO = Decimal("0.02")  # tolerancia para validar netos impresos


def num(s):
    """'1.234,56' o '1234,56' -> Decimal."""
    return Decimal(s.replace(".", "").replace(",", "."))


def texto_pdf(path):
    return subprocess.run(
        ["pdftotext", "-raw", "-enc", "UTF-8", str(path), "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")


# ---------------------------------------------------------------- catálogo
def leer_catalogo():
    """(producto, presentación) -> cantidad base (g, ml o unidad)."""
    cat = {}
    with open(BASE / "catalogo.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            cat[(r["producto"], r["presentacion"])] = Decimal(r["cantidad_base"])
    return cat


def leer_rendimientos():
    rend = {}
    with open(BASE / "rendimientos.csv", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rend[r["producto"]] = (Decimal(r["limpio_sobre_bruto"]),
                                   Decimal(r["cocido_sobre_limpio"]))
    return rend


# ---------------------------------------------------------------- facturas
# Las facturas traen las columnas en distinto orden: se mapean por encabezado.
COLUMNAS = {"Cant.": "cantidad", "Unidad": "presentacion",
            "P. unitario": "precio", "Bonif.%": "bonif", "Neto": "neto"}


def leer_factura(path):
    txt = texto_pdf(path)
    ident = re.search(r"Factura (F-\d+)", txt).group(1)
    fecha = re.search(r"Fecha: (\d{4}-\d{2}-\d{2})", txt).group(1)
    enc = re.search(r"^R C\S+ / descripci\S+ (.+)$", txt, re.M).group(1)
    orden = [COLUMNAS[c] for c in re.findall(r"Cant\.|Unidad|P\. unitario|Bonif\.%|Neto", enc)]
    assert len(orden) == 5, (path, enc)

    renglones = {}
    for m in re.finditer(r"^(\d+) ([A-Z]\d{2}) (.+)$", txt, re.M):
        tokens = m.group(3).split()
        campos = dict(zip(orden, tokens[-5:]))
        r = {
            "renglon": int(m.group(1)),
            "producto": m.group(2),
            "descripcion": " ".join(tokens[:-5]),
            "presentacion": campos["presentacion"],
            "cantidad": num(campos["cantidad"]),
            "precio": num(campos["precio"]),
            "bonif": num(campos["bonif"]),
            "neto": num(campos["neto"]),
        }
        # Control: neto = cantidad x precio x (1 - bonif)
        esperado = r["cantidad"] * r["precio"] * (1 - r["bonif"] / 100)
        if abs(esperado - r["neto"]) > TOL_NETO:
            print(f"AVISO {ident} renglón {r['renglon']}: neto {r['neto']} "
                  f"vs calculado {esperado:.4f}", file=sys.stderr)
        renglones[r["renglon"]] = r

    total = re.search(r"TOTAL \$ ([\d.,]+)", txt)
    if total and abs(num(total.group(1)) - sum(r["neto"] for r in renglones.values())) > TOL_NETO:
        print(f"AVISO {ident}: total no coincide con la suma de netos", file=sys.stderr)
    return {"id": ident, "fecha": fecha, "renglones": renglones}


# ---------------------------------------------------------------- notas
def leer_nota(path):
    txt = texto_pdf(path)
    cant = re.search(r"Cantidad devuelta: ([\d.,]+) (\S+)", txt)
    return {
        "id": re.search(r"Nota de cr\S+ (NC-\d+)", txt).group(1),
        "fecha": re.search(r"Fecha: (\d{4}-\d{2}-\d{2})", txt).group(1),
        "factura": re.search(r"Factura asociada: (F-\d+)", txt).group(1),
        "renglon": int(re.search(r"Rengl\S+: (\d+)", txt).group(1)),
        "producto": re.search(r"Producto: ([A-Z]\d{2})", txt).group(1),
        "concepto": re.search(r"Concepto: (\S+)", txt).group(1),
        "cantidad": num(cant.group(1)),
        "presentacion": cant.group(2),
        "importe": num(re.search(r"Importe acreditado: \$ ([\d.,]+)", txt).group(1)),
    }


# ---------------------------------------------------------------- precios
def precios_unitarios(cat):
    facturas = [leer_factura(p) for p in sorted((BASE / "facturas").glob("*.pdf"))]
    notas = [leer_nota(p) for p in sorted((BASE / "notas").glob("*.pdf"))]

    # Cantidad equivalente e importe neto por renglón.
    lineas = {}
    for fac in facturas:
        if fac["fecha"] > FECHA_COSTEO:
            continue
        for r in fac["renglones"].values():
            lineas[(fac["id"], r["renglon"])] = {
                "producto": r["producto"], "fecha": fac["fecha"], "factura": fac["id"],
                "neto": r["neto"],
                "cantidad": r["cantidad"] * cat[(r["producto"], r["presentacion"])],
            }

    # Documentos asociados emitidos hasta la fecha de costeo: ajustan su renglón.
    for n in notas:
        if n["fecha"] > FECHA_COSTEO:
            continue
        ln = lineas.get((n["factura"], n["renglon"]))
        if ln is None:
            continue
        assert ln["producto"] == n["producto"], n
        ln["neto"] -= n["importe"]  # bonificación y devolución restan importe
        if n["concepto"].lower().startswith("devoluci"):
            ln["cantidad"] -= n["cantidad"] * cat[(n["producto"], n["presentacion"])]

    # Última factura <= fecha; a igual fecha gana el id alfanuméricamente mayor.
    elegido = {}
    for ln in lineas.values():
        clave = (ln["fecha"], ln["factura"])
        prev = elegido.get(ln["producto"])
        if prev is None or clave > (prev["fecha"], prev["factura"]):
            elegido[ln["producto"]] = dict(ln)
        elif clave == (prev["fecha"], prev["factura"]):  # mismo producto repetido en la factura
            prev["neto"] += ln["neto"]
            prev["cantidad"] += ln["cantidad"]
    return {p: v["neto"] / v["cantidad"] for p, v in elegido.items()}, elegido


# ---------------------------------------------------------------- recetas
def calcular(precios, rend):
    recetas = {r["codigo"]: r for r in json.load(open(BASE / "recetas.json", encoding="utf-8"))}
    memo = {}

    def costo_unitario_prep(cod):
        """Costo por g/ml de la tanda terminada de una preparación."""
        if cod not in memo:
            r = recetas[cod]
            memo[cod] = costo_receta(r) / Decimal(str(r["rendimiento"]))
        return memo[cod]

    def costo_ing(i):
        q = Decimal(str(i["cantidad"]))
        p = i["producto"]
        if i["estado"] == "preparado":
            return q * costo_unitario_prep(p)
        lb, cl = rend[p]
        if i["estado"] == "limpio":
            q = q / lb
        elif i["estado"] == "cocido":
            q = q / cl / lb
        return q * precios[p]

    def costo_receta(r):
        return sum(costo_ing(i) for i in r["ingredientes"])

    platos = {c: costo_receta(r) / Decimal(str(r["rendimiento"]))
              for c, r in recetas.items() if c.startswith("P")}
    return platos


def main():
    cat = leer_catalogo()
    rend = leer_rendimientos()
    precios, origen = precios_unitarios(cat)
    platos = calcular(precios, rend)
    with open(BASE / "costos.csv", "w", encoding="utf-8", newline="") as f:
        f.write("plato,costo_por_porcion\n")
        for c in sorted(platos):
            v = platos[c].quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            f.write(f"{c},{v}\n")
    if "-v" in sys.argv:
        for p in sorted(precios):
            o = origen[p]
            print(f"{p} {o['factura']} {o['fecha']} neto={o['neto']} cant={o['cantidad']} "
                  f"pu={precios[p]:.6f}")


if __name__ == "__main__":
    main()
