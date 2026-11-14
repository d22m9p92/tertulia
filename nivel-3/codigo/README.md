# Nivel 3 · Compras, caja y márgenes

`python costeo_n3.py <datos_nivel_2> <datos_nivel_3> nivel-3` genera `costos.csv` y `margenes.csv`.

- **Compras**: facturas PDF del nivel 2 (F-001..F-040, con NC-001..NC-004) más las imágenes del nivel 3, transcritas a `compras_ocr.csv`: remitos manuscritos M-001..M-012 y tickets T-001..T-015. En los manuscritos se tomó el valor corregido, no el tachado. Cada renglón se valida con cantidad × precio × (1 − bonif) = neto y con el umbral de bonificación.
- **Precio a una fecha D**: última compra por producto con fecha ≤ D (si empatan, gana el id mayor, por ejemplo T-005 sobre T-001), con las notas emitidas hasta D. Una bonificación resta importe; una devolución resta importe y cantidad.
- **costos.csv**: costo por porción con D = 31/10/2026. Las recetas y la conversión limpio/cocido son las del nivel 2 (`costeo_n2.py`).
- **margenes.csv**: VTA usa el artículo vigente a la fecha para obtener el plato. COM reparte el cobro neto (bruto − descuento) según `peso_ingreso`, y el costo usa las unidades de cada componente. REV resta el reparto, las unidades y el costo del movimiento original, a la fecha original. EXT (propinas) queda afuera. El costo de cada venta se calcula con los precios a su propia fecha. Margen = (ingreso − costo) / ingreso, con 6 decimales.
