"""Nivel 3: costos al cierre (31/10/2026) y márgenes trimestrales con costo histórico.

Uso: python costeo_n3.py <datos_n2> <datos_n3> <salida_dir>
- <datos_n2>: recetas.json, catalogo.csv, rendimientos.csv, facturas/F-*.pdf, notas/NC-*.pdf
- <datos_n3>: caja/ (2026-08/09/10.csv, articulos.csv, combos.csv)
- compras_ocr.csv (junto a este script): transcripción de facturas/*.jpg (M-001..M-012) y
  tickets/*.jpg (T-001..T-015), con precio y bonificación para validar cada neto.
"""
import csv, os, sys
from collections import defaultdict
from decimal import Decimal as D, ROUND_HALF_UP
import costeo_n2 as n2

AQUI = os.path.dirname(os.path.abspath(__file__))

def cargar_compras(base2, cat):
    """Lista de renglones {doc, fecha, producto, base, neto} y lista de notas."""
    renglones = {}
    import glob
    for p in sorted(glob.glob(os.path.join(base2, "facturas", "*.pdf"))):
        fid, fecha, ren = n2.leer_factura(p, cat)
        for k, r in ren.items():
            renglones[(fid, k)] = {"doc": fid, "fecha": fecha, "producto": r["producto"],
                                   "base": r["base"], "neto": r["neto"]}
    cnt = defaultdict(int)
    for r in csv.DictReader(open(os.path.join(AQUI, "compras_ocr.csv"), encoding="utf-8")):
        q, p, b, neto = D(r["cantidad"]), D(r["precio"]), D(r["bonif"]), D(r["neto"])
        assert abs(q * p * (1 - b / 100) - neto) <= D("0.02"), r  # control de la transcripción
        cnt[r["doc"]] += 1
        renglones[(r["doc"], cnt[r["doc"]])] = {"doc": r["doc"], "fecha": r["fecha"], "producto": r["producto"],
                                                "base": q * cat[(r["producto"], r["presentacion"])], "neto": neto}
    notas = [n2.leer_nota(p, cat) for p in sorted(glob.glob(os.path.join(base2, "notas", "*.pdf")))]
    return renglones, notas

def precios_a(fecha, renglones, notas):
    """Precio efectivo por producto con compras y notas emitidas hasta `fecha` (inclusive)."""
    aj = {k: [v["neto"], v["base"]] for k, v in renglones.items()}
    for n in notas:
        if n["fecha"] <= fecha:
            a = aj[(n["factura"], n["renglon"])]
            a[0] -= n["importe"]
            if n["concepto"].lower().startswith("devoluci"):
                a[1] -= n["cant_base"]
    mejor = {}
    for k, r in renglones.items():
        if r["fecha"] > fecha:
            continue
        clave = (r["fecha"], r["doc"])
        if r["producto"] not in mejor or clave > mejor[r["producto"]][0]:
            mejor[r["producto"]] = (clave, aj[k][0] / aj[k][1])
    return {p: v[1] for p, v in mejor.items()}

def costos_platos(fecha, recetas, rend, renglones, notas):
    precio = precios_a(fecha, renglones, notas)
    memo = {}
    return {c: n2.costo(c, recetas, rend, precio, memo) / D(str(r["rendimiento"]))
            for c, r in recetas.items() if r["unidad_rendimiento"] == "porción"}

def q2(x): return x.quantize(D("0.01"), ROUND_HALF_UP)

def main(base2, base3, out):
    cat, rend, recetas = n2.cargar(base2)
    renglones, notas = cargar_compras(base2, cat)
    platos = [c for c, r in recetas.items() if r["unidad_rendimiento"] == "porción"]

    cierre = costos_platos("2026-10-31", recetas, rend, renglones, notas)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "costos.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("plato,costo_por_porcion\n")
        for c in platos:
            f.write(f"{c},{q2(cierre[c])}\n")

    caja = os.path.join(base3, "caja")
    art = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(caja, "articulos.csv"), encoding="utf-8")):
        art[r["articulo"]].append(r)
    combos = defaultdict(list)
    for r in csv.DictReader(open(os.path.join(caja, "combos.csv"), encoding="utf-8")):
        combos[r["combo"]].append((r["plato"], D(r["unidades"]), D(r["peso_ingreso"])))
    movs = []
    for m in ("2026-08", "2026-09", "2026-10"):
        movs += list(csv.DictReader(open(os.path.join(caja, m + ".csv"), encoding="utf-8")))
    por_id = {r["id"]: r for r in movs}

    costos_dia = {}
    def costo_dia(d):
        if d not in costos_dia:
            costos_dia[d] = costos_platos(d, recetas, rend, renglones, notas)
        return costos_dia[d]

    def efecto(r):
        """Reparto (plato, unidades, ingreso, costo) de una VTA/COM a su fecha."""
        d = r["fecha_hora"][:10]
        cant = D(r["cantidad"])
        cobro = D(r["importe_bruto"]) - D(r["descuento"])
        cd = costo_dia(d)
        if r["tipo"] == "VTA":
            plato = next(a["plato"] for a in art[r["articulo"]] if a["desde"] <= d <= a["hasta"])
            return [(plato, cant, cobro, cant * cd[plato])]
        comps = combos[r["articulo"]]
        tot = sum(p for _, _, p in comps)
        return [(pl, cant * u, cobro * p / tot, cant * u * cd[pl]) for pl, u, p in comps]

    agg = {c: [D(0), D(0), D(0)] for c in platos}
    for r in movs:
        if r["tipo"] in ("VTA", "COM"):
            signo, base_mov = 1, r
        elif r["tipo"] == "REV":
            signo, base_mov = -1, por_id[r["referencia"]]  # reparto y costo del original
        else:
            continue  # EXT: propina, no es facturación de platos
        for pl, u, ing, cst in efecto(base_mov):
            a = agg[pl]
            a[0] += signo * u; a[1] += signo * ing; a[2] += signo * cst

    with open(os.path.join(out, "margenes.csv"), "w", encoding="utf-8", newline="") as f:
        f.write("plato,unidades_vendidas,ingreso_neto,costo,margen\n")
        for c in platos:
            u, ing, cst = agg[c]
            mg = (ing - cst) / ing if ing != 0 else D(0)
            f.write(f"{c},{int(u)},{q2(ing)},{q2(cst)},{mg.quantize(D('0.000001'), ROUND_HALF_UP)}\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
