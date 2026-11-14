# Nivel 2 · Costo por porción al 31/10/2026

El script `costeo.py` genera `nivel-2/costos.csv` con el costo de ingredientes de los 50 platos (`P01`–`P50`). Las subrecetas (`S01`–`S15`) se calculan como pasos intermedios, pero no aparecen como filas.

## Entradas (todas en `nivel-2/`)

| Archivo | Uso |
|---|---|
| `recetas.json` | Platos y preparaciones: ingredientes, cantidad, unidad, estado (`bruto`, `limpio`, `cocido`, `preparado`) y rendimiento de la tanda. |
| `catalogo.csv` | Cantidad base (g, ml o unidad) de cada presentación de cada producto. Con esto se pasa la cantidad facturada a cantidad equivalente. |
| `rendimientos.csv` | Cocientes `limpio_sobre_bruto` y `cocido_sobre_limpio` por producto. |
| `facturas/F-*.pdf` | 40 facturas. Cada una trae fecha, renglones, presentación, cantidad, precio, bonificación y neto. |
| `notas/NC-*.pdf` | Notas de crédito asociadas a una factura y un renglón: bonificación o devolución. |

## Cómo reproduce el cálculo

1. **Lectura de PDF.** Cada PDF se convierte a texto con `pdftotext -raw` (Poppler). Las facturas no traen las columnas siempre en el mismo orden. Por eso el orden de *Cant., Unidad, P. unitario, Bonif.%, Neto* se toma del encabezado de cada factura, y los últimos cinco campos de cada renglón se asignan según ese orden. Como control, se verifica que `neto ≈ cantidad × precio × (1 − bonif)` y que la suma de netos dé el TOTAL. En este lote, todas las facturas pasan el control.
2. **Cantidad equivalente.** Por renglón se calcula `cantidad × cantidad_base(producto, presentación)`, con la cantidad base del catálogo.
3. **Notas de crédito.** Se aplican las notas con fecha menor o igual al 31/10/2026, cada una sobre su factura y renglón de origen. No cuentan como compras nuevas.
   - Una *bonificación* resta el importe acreditado y deja la cantidad igual.
   - Una *devolución* resta el importe y también las unidades devueltas, convertidas con el catálogo.
4. **Factura vigente por producto.** Para cada producto se toma la factura con la fecha más reciente que no pase el 31/10/2026. Si dos facturas tienen la misma fecha, gana el identificador alfanuméricamente mayor. El precio unitario efectivo es el neto ajustado dividido por la cantidad equivalente ajustada.
5. **Paso a bruto.** Un ingrediente en estado `bruto` queda igual. Uno `limpio` se divide por `limpio_sobre_bruto`. Uno `cocido` se divide por `cocido_sobre_limpio` y después por `limpio_sobre_bruto`. Cereales y legumbres tienen un coeficiente de cocción mayor que 1 porque absorben agua.
6. **Preparaciones.** El costo de una tanda es la suma de sus ingredientes. El costo por g o ml es ese total dividido por el rendimiento final de la tanda (por ejemplo, el caldo rinde 4000 ml). El agua no tiene costo. Las preparaciones que usan otras preparaciones se resuelven de forma recursiva, guardando cada resultado para no recalcularlo.
7. **Plato.** Se suman todos los ingredientes con `Decimal`, sin redondeos intermedios. Al final se redondea a 2 decimales con la mitad hacia arriba.

Facturas vigentes en este lote:

| Proveedor | Factura | Fecha | Nota aplicada |
|---|---|---|---|
| Huerta del Andén | F-037 | 24/10 | — |
| Frigorífico del Muelle | F-038 | 24/10 | — |
| Almacén del Molino Azul | F-039 | 24/10 | NC-003, bonificación del renglón 3 (lenteja) |
| Granja La Ochava | F-040 | 24/10 | NC-004, devolución de 36 huevos del renglón 5 |

NC-001 (sobre F-005) y NC-002 (sobre F-022) ajustan facturas que después fueron reemplazadas por compras más recientes, así que no cambian el resultado.

## Ejecución

Desde la raíz del repositorio:

```bash
python nivel-2/codigo/costeo.py      # escribe nivel-2/costos.csv
python nivel-2/codigo/costeo.py -v   # además muestra la factura y el precio unitario de cada producto
```

Requisitos: Python 3.8 o superior, solo con la biblioteca estándar, y `pdftotext` (Poppler) en el PATH.
