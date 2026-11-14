"""Costeo de la carta de El Término Medio al 31/10/2026 (nivel 2).

Uso: python costeo.py <carpeta_datos> <salida.csv>
<carpeta_datos> contiene recetas.json, catalogo.csv, rendimientos.csv,
facturas/*.pdf y notas/*.pdf. Requiere pdftotext (poppler-utils).
"""
import csv, json, re, subprocess, sys, glob, os
from decimal import Decimal as D, ROUND_HALF_UP

FECHA_COSTEO = "2026-10-31"

def num(s):
    return D(s.replace(".", "").replace(",", ".")) if "," in s else D(s)

def pdf_text(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout

def cargar(base):
    cat = {(r["producto"], r["presentacion"]): D(r["cantidad_base"])
           for r in csv.DictReader(open(os.path.join(base, "catalogo.csv"), encoding="utf-8"))}
    rend = {r["producto"]: (D(r["limpio_sobre_bruto"]), D(r["cocido_sobre_limpio"]))
            for r in csv.DictReader(open(os.path.join(base, "rendimientos.csv"), encoding="utf-8"))}
    recetas = {r["codigo"]: r for r in json.load(open(os.path.join(base, "recetas.json"), encoding="utf-8"))}
    return cat, rend, recetas

def leer_factura(path, cat):
    """Devuelve id, fecha y renglones {nro: dict}. El orden de columnas varía por
    factura, así que se mapea según el encabezado."""
    t = pdf_text(path)
    fid = re.search(r"Factura (F-\d+)", t).group(1)
    fecha = re.search(r"Fecha:\s*(\d{4}-\d{2}-\d{2})", t).group(1)
    cols = None
    renglones = {}
    for line in t.splitlines():
        partes = re.split(r"\s{2,}", line.strip())
        if partes and partes[0] == "R" and "Neto" in line:
            # "R | Código / descripción | ..." -> columnas tras la descripción
            cols = partes[2:]
            continue
        if cols and len(partes) == 2 + len(cols) and partes[0].isdigit():
            v = dict(zip(cols, partes[2:]))
            prod = partes[1].split()[0]
            pres = v["Unidad"]
            q = num(v["Cant."])
            renglones[int(partes[0])] = {
                "producto": prod, "presentacion": pres, "cantidad": q,
                "precio": num(v["P. unitario"]), "bonif": num(v["Bonif.%"]),
                "neto": num(v["Neto"]), "base": q * cat[(prod, pres)],
            }
    return fid, fecha, renglones

def leer_nota(path, cat):
    t = pdf_text(path)
    g = lambda pat: re.search(pat, t).group(1)
    prod = g(r"Producto:\s*(\S+)")
    qty, unit = re.search(r"Cantidad devuelta:\s*([\d.,]+)\s*(\S+)", t).groups()
    return {
        "id": g(r"Nota de crédito (\S+)"), "fecha": g(r"Fecha:\s*(\d{4}-\d{2}-\d{2})"),
        "factura": g(r"Factura asociada:\s*(\S+)"), "renglon": int(g(r"Renglón:\s*(\d+)")),
        "producto": prod, "concepto": g(r"Concepto:\s*(\S+)"),
        "cant_base": num(qty) * cat[(prod, unit)],
        "importe": num(g(r"Importe acreditado:\s*\$\s*([\d.,]+)")),
    }

def precios(base, cat):
    facturas = {}
    for p in sorted(glob.glob(os.path.join(base, "facturas", "*.pdf"))):
        fid, fecha, ren = leer_factura(p, cat)
        facturas[fid] = (fecha, ren)
    # notas: ajustan su factura/renglón de origen (no son compras nuevas)
    for p in sorted(glob.glob(os.path.join(base, "notas", "*.pdf"))):
        n = leer_nota(p, cat)
        if n["fecha"] > FECHA_COSTEO:
            continue
        r = facturas[n["factura"]][1][n["renglon"]]
        assert r["producto"] == n["producto"]
        r["neto"] -= n["importe"]
        if n["concepto"].lower().startswith("devoluci"):
            r["base"] -= n["cant_base"]
    # última factura <= fecha por producto; empate -> id mayor
    elegido = {}
    for fid, (fecha, ren) in facturas.items():
        if fecha > FECHA_COSTEO:
            continue
        for r in ren.values():
            k = (fecha, fid)
            if r["producto"] not in elegido or k > elegido[r["producto"]][0]:
                elegido[r["producto"]] = (k, r["neto"] / r["base"])
    return {p: v[1] for p, v in elegido.items()}, elegido

def costo(codigo, recetas, rend, precio, memo={}):
    """Costo de la tanda/porción completa de una receta."""
    if codigo in memo:
        return memo[codigo]
    total = D(0)
    for i in recetas[codigo]["ingredientes"]:
        p, q, e = i["producto"], D(str(i["cantidad"])), i["estado"]
        if p in recetas:  # subreceta: costo por unidad de su rendimiento final
            total += costo(p, recetas, rend, precio) / D(str(recetas[p]["rendimiento"])) * q
            continue
        lb, cl = rend[p]
        if e == "limpio":
            q /= lb
        elif e == "cocido":
            q /= lb * cl
        total += q * precio[p]
    memo[codigo] = total
    return total

def main(base, salida):
    cat, rend, recetas = cargar(base)
    precio, _ = precios(base, cat)
    with open(salida, "w", encoding="utf-8", newline="") as f:
        f.write("plato,costo_por_porcion\n")
        for c, r in recetas.items():
            if r["unidad_rendimiento"] != "porción":
                continue
            v = costo(c, recetas, rend, precio) / D(str(r["rendimiento"]))
            f.write(f"{c},{v.quantize(D('0.01'), ROUND_HALF_UP)}\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
