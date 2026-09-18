# Guía para explicar FactuGuard IA

Esta guía resume **dónde está cada inteligencia artificial en el código**, qué hace y cómo defenderla en una exposición. Los números de la sección 4 se midieron ejecutando el proyecto (18-sep-2026).

## 1. Flujo completo de una factura

```
Factura (CSV / Excel / PDF / formulario / experimento sintético)
   │
   ▼
servicio.py  ──►  preparar_facturas_cargadas()      valida y normaliza columnas
   │
   ├─► reglas_negocio.py   aplicar_reglas()          REGLAS  (sistema experto, no aprende)
   │
   ├─► servicio.aplicar_modelos_ia()  (línea 63)     tres opiniones de IA:
   │      ├─ detector_ia.py         IA 1  Isolation Forest   (no supervisada)
   │      ├─ detector_knn.py        IA 2  KNN, K = 5         (supervisada)
   │      └─ detector_perceptron.py IA 3  Perceptrón         (supervisada, una neurona)
   │
   ▼
alerta_hibrida = alerta_reglas  OR  alerta_isolation  OR  alerta_knn  OR  alerta_perceptron
   │
   ▼
Persona revisa  ──►  recomendador_ia.py  (IA 4 lógica difusa + IA 5 neurona que aprende de la persona)
```

Regla de oro para explicarlo: **la alerta se dispara si CUALQUIERA de las cuatro opiniones encuentra riesgo (OR)**. Es una decisión de diseño: prioriza no dejar pasar anomalías (exhaustividad) a costa de más falsas alarmas.

## 2. Dónde está cada componente

| # | Componente | Archivo y punto exacto | Tipo | Aprende de |
|---|-----------|------------------------|------|-----------|
| 0 | Reglas de negocio | [reglas_negocio.py:12](reglas_negocio.py#L12) `aplicar_reglas` | Sistema experto (reglas `if`) | Nada: son reglas escritas a mano |
| 1 | Isolation Forest | [detector_ia.py:13](detector_ia.py#L13) `DetectorAnomalias` | ML **no supervisado** | 7.000 facturas normales; umbral = percentil 99 (línea 44) |
| 2 | KNN | [detector_knn.py:12](detector_knn.py#L12) `DetectorKNN` | ML **supervisado** por proximidad | 120 normales + 60 anómalas etiquetadas |
| 3 | Perceptrón | [detector_perceptron.py:17](detector_perceptron.py#L17) `DetectorPerceptron` | Red neuronal de **una** neurona, hecha desde cero con NumPy | Los mismos 180 ejemplos etiquetados |
| 4 | Riesgo difuso | [recomendador_ia.py:114](recomendador_ia.py#L114) `riesgo_difuso` | Lógica difusa + centroide | Nada: funciones de pertenencia fijas |
| 5 | Neurona de aprobación | [recomendador_ia.py:41](recomendador_ia.py#L41) `NeuronaAprobacion` | Neurona logística (sigmoide) con descenso de gradiente | Decisiones humanas (aprobar/rechazar); se guarda en `resultados/neurona_aprobacion.json` |
| — | Combinación de las 3 IA | [servicio.py:63](servicio.py#L63) `aplicar_modelos_ia` | Orquestación | — |
| — | Ejemplos etiquetados de KNN y perceptrón | [servicio.py:31](servicio.py#L31) `preparar_ejemplos_supervisados` | Datos | — |

Las 7 variables que ven los modelos están en [config.py:20](config.py#L20): `cantidad, precio_unitario, descuento_pct, valor_descuento, subtotal, total, hora`.

### Cómo explicar cada una en 20 segundos

- **Reglas:** «Comprueban cosas que sabemos que están mal: IVA distinto de 19 %, subtotal + IVA ≠ total, número repetido, hora fuera de 7-19. No aprenden; por eso son 100 % explicables.»
- **Isolation Forest:** «Nunca vio una anomalía. Aprendió cómo es una factura normal y marca las que son fáciles de aislar con cortes aleatorios, porque están lejos de lo normal.» (Puntaje en `puntaje_ia`, alerta si supera el percentil 99 de las normales.)
- **KNN:** «Guarda 180 ejemplos etiquetados. Para una factura nueva mira sus 5 vecinos más parecidos y vota. Hay que escalar las variables (`StandardScaler`) porque pesos, porcentajes y horas tienen unidades distintas.» (`weights="distance"`: el vecino más cercano pesa más.)
- **Perceptrón:** «Una neurona: `Z = X·W + b`; si `Z ≥ 0` alerta (función escalón). Cuando se equivoca, corrige pesos: `W += tasa · error · X`.» El bucle está en [detector_perceptron.py:62](detector_perceptron.py#L62).
- **Difuso:** «Convierte la severidad en tres conjuntos (bajo, medio, alto) y calcula un porcentaje de riesgo con el centroide.»
- **Neurona de aprobación:** «Cada vez que una persona aprueba o rechaza una propuesta, se ajustan los pesos; así el sistema aprende qué recomendaciones le resultan útiles al analista.» ([web_app.py](web_app.py) llama a `aprender_de_decision` tras cada decisión.)

## 3. Dónde se ve en la interfaz

- **Resumen:** tarjeta «Dónde y cómo usa IA FactuGuard» (las 4 opiniones + persona).
- **Prueba manual:** al analizar una factura muestra la opinión de reglas, Isolation Forest, KNN (con % de similitud a alertas) y perceptrón (con su `Z`).
- **Alertas / Ver factura:** el texto del motivo dice qué modelo alertó; la factura muestra insignias por modelo.
- **Recomendar:** riesgo difuso, confianza y probabilidad de aprobación (neurona 5).

## 4. Qué tan bien funciona (números reales, dilo con honestidad)

En la pantalla aparece **F1 = 100 %** sobre 30 facturas. Es cierto pero **no es una medida de desempeño real**: son pocas, sintéticas, y las anomalías de prueba salen del mismo generador que produce los ejemplos de KNN y perceptrón.

Prueba ampliada (2.000 facturas normales nuevas + 600 anómalas nuevas):

| Componente | Detecta (recall) | Falsos positivos (de 2.000 normales) | Precisión |
|---|---|---|---|
| Reglas | 66,7 % | 0 | 100 % |
| Isolation Forest | 18,0 % | 23 (1,2 %) | 82 % |
| KNN | 46,2 % | 125 (6,3 %) | 69 % |
| Perceptrón | 38,8 % | 3 (0,15 %) | 99 % |
| **Híbrido (OR de todos)** | **99,5 %** | **149 (7,5 %)** | **80 %** |

Lectura para la exposición:

1. **Las reglas cubren** IVA, aritmética, duplicados y horario (cuatro de los seis tipos de anomalía inyectados: 12 de las 18 anomalías de prueba). La IA **no** detecta esos casos por sí sola (recall ≈ 0-8 % en ellos).
2. **La IA aporta lo que las reglas no ven:** `monto_atipico` (97 % detectado por IA) y `descuento_atipico` (100 %), que no tienen una regla exacta.
3. **El precio de combinar con OR** es ~7 % de falsas alarmas, casi todas de KNN. Por eso existe la revisión humana.
4. **El perceptrón no converge** con estos datos: comete ~36 errores sobre sus 180 ejemplos de entrenamiento. Es esperable: una sola neurona solo separa con una línea recta, y un monto anómalo puede ser demasiado alto **o** demasiado bajo (problema no lineal, parecido al XOR). Es un buen punto para explicar el límite del perceptrón y por qué existen redes multicapa.

## 5. Limitaciones conocidas (sé tú quien las menciona)

- Los datos son **sintéticos**; con facturas reales habría que recalibrar umbrales y volver a evaluar.
- La regla de IVA marca todo lo distinto de 19 %, pero en Colombia existen tarifas legítimas de 0 % y 5 %.
- La regla de duplicados compara contra los IDs sintéticos `FAC-C-xxxxx` y dentro del mismo archivo. **No detecta duplicados entre cargas distintas**: `guardar_carga_archivo` reemplaza la versión anterior del mismo documento en lugar de alertar.
- No se valida la factura ante la DIAN (el propio sistema lo declara).

## 6. Antes de ponerlo en un servidor

1. **CSRF:** ningún formulario POST tiene token. Añadir Flask-WTF `CSRFProtect`.
2. **Servidor de producción:** `app.run` es solo para desarrollo. Usar `waitress` (Windows) o `gunicorn` (Linux) y HTTPS.
3. **`FLASK_SECRET_KEY` obligatoria** en el `.env` del servidor; si falta, cada reinicio invalida las sesiones.
4. **Cookies de sesión:** activar `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY` y `SESSION_COOKIE_SAMESITE`.
5. **Autorización:** cualquier usuario autenticado puede abrir `/factura-cargada/<id>` de otro usuario; la columna `rol` existe pero no se usa.
6. **Errores:** varias vistas muestran `{error}` de PostgreSQL al usuario. En producción registrar el error y mostrar un mensaje genérico.
7. **Intentos de login:** no hay límite; añadir bloqueo temporal.
8. **`neurona_aprobacion.json`** es un archivo local compartido: con varios procesos puede corromperse y en hosting efímero se pierde. Moverlo a PostgreSQL.
9. **Dependencias:** fijar versiones en `requirements.txt`.
10. `app.py` (Tkinter) es la versión antigua de escritorio: solo usa Isolation Forest. La aplicación vigente es `web_app.py`.
