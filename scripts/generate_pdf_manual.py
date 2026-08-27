import os
import sys
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

def build_pdf(filename="docs/audits/MANUAL_FUNCIONAL_MODULOS_Y_REGLAS_EDUAGRO.pdf"):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    doc = SimpleDocTemplate(
        filename,
        pagesize=letter,
        leftMargin=36,
        rightMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette
    COLOR_PRIMARY = colors.HexColor("#1b4332")     # Deep Forest Green
    COLOR_SECONDARY = colors.HexColor("#2d6a4f")   # Medium Green
    COLOR_ACCENT = colors.HexColor("#d8f3dc")      # Light Mint
    COLOR_DARK = colors.HexColor("#212529")        # Dark Charcoal Text
    COLOR_MUTED = colors.HexColor("#495057")       # Muted Text
    COLOR_LIGHT_BG = colors.HexColor("#f8f9fa")   # Table / Card Light Gray
    COLOR_WARNING = colors.HexColor("#b7094c")    # Deep Red / Warning Accent

    # Custom Paragraph Styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=22,
        leading=26,
        textColor=COLOR_PRIMARY,
        alignment=0,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=11,
        leading=15,
        textColor=COLOR_MUTED,
        spaceAfter=15
    )

    h1_style = ParagraphStyle(
        'SectionH1',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=COLOR_PRIMARY,
        spaceBefore=14,
        spaceAfter=8,
        keepWithNext=True
    )

    h2_style = ParagraphStyle(
        'SectionH2',
        parent=styles['Heading3'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=16,
        textColor=COLOR_SECONDARY,
        spaceBefore=10,
        spaceAfter=4,
        keepWithNext=True
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=COLOR_DARK,
        spaceAfter=6
    )

    bullet_style = ParagraphStyle(
        'BulletText',
        parent=body_style,
        leftIndent=12,
        spaceAfter=4
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=11,
        textColor=colors.white
    )

    table_cell_style = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=COLOR_DARK
    )

    story = []

    # Document Header
    story.append(Paragraph("🌾 EduAgro - Manual de Módulos y Reglas de Decisión", title_style))
    story.append(Paragraph("<b>Destinatario:</b> Socio Estratégico & Equipo de Agronomía | <b>Ámbito:</b> Lógica Funcional, Conexión de Módulos y Agentes Inteligentes", subtitle_style))
    story.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_PRIMARY, spaceBefore=0, spaceAfter=12))

    # SECTION 1
    story.append(Paragraph("1. Estructura de Módulos Funcionales (Qué guarda la aplicación)", h1_style))
    story.append(Paragraph(
        "EduAgro está estructurada en módulos funcionales orientados al negocio agropecuario. "
        "A continuación se detalla la información que gestiona y almacena cada módulo de la plataforma:",
        body_style
    ))

    modulos_data = [
        [
            Paragraph("Módulo Funcional", table_header_style),
            Paragraph("Información y Objetos de Negocio Almacenados", table_header_style)
        ],
        [
            Paragraph("<b>1. Lotes y Producción</b>", table_cell_style),
            Paragraph("Establecimientos (campos), lotes productivos con su delimitación geográfica, superficie cultivable (ha), historia de cultivos por campaña (soja, maíz, trigo, sorgo), rendimientos estimados ($qq/ha$) y rendimientos reales post-cosecha.", table_cell_style)
        ],
        [
            Paragraph("<b>2. Stock Físico y Acopios</b>", table_cell_style),
            Paragraph("Ubicaciones de almacenamiento (silos propios, silobolsas en campo, celdas, acopios y cooperativas en custodia). Partidas trazables de grano con fecha de cosecha, lote de origen, tipo de grano, peso real ($\mathrm{kg}$), mediciones de calidad (humedad \%, temperatura) y movimientos de inventario.", table_cell_style)
        ],
        [
            Paragraph("<b>3. Comercial y Contratos</b>", table_cell_style),
            Paragraph("Contratos de venta de granos a precio fijo y ventas 'A Fijar' Pizarra, compromisos comerciales de entrega, compradores/puertos consignatarios, fechas de vencimiento y volumen pactado en toneladas.", table_cell_style)
        ],
        [
            Paragraph("<b>4. Arrendamientos Agrícolas</b>", table_cell_style),
            Paragraph("Contratos de alquiler de campo en producto ($qq/ha$), conversión a quintales totales y toneladas equivalentes ($1\ \mathrm{Tn} = 10\ \mathrm{qq}$), y valorización en USD según base Rosario directo o Acopio (deduciendo flete y comisión).", table_cell_style)
        ],
        [
            Paragraph("<b>5. Logística, Fletes y Cartas de Porte</b>", table_cell_style),
            Paragraph("Tarifarios de fletes por transportista y destino, estado de caminos rurales (transitables/intransitables), turnos y cupos asignados, cartas de porte oficiales, validez de pesaje de origen (bruto y tara) y pesaje en balanza de destino.", table_cell_style)
        ],
        [
            Paragraph("<b>6. Agrometeorología y Clima</b>", table_cell_style),
            Paragraph("Pronósticos agrometeorológicos geolocalizados por campo (Google Weather y Open-Meteo), lluvia acumulada proyectada a 24h/72h ($mm$), velocidad máxima de viento y ráfagas ($km/h$), temperatura mínima/máxima ($^\circ C$) y nivel de coincidencia entre fuentes climáticas.", table_cell_style)
        ],
        [
            Paragraph("<b>7. Insumos y Depósito</b>", table_cell_style),
            Paragraph("Catálogo de semillas, fitosanitarios, fertilizantes, combustibles y repuestos. Saldo por depósito, Precio Promedio Ponderado Móvil (PPP en USD/ARS), historial de compras, transferencias y reservas para labores agrícolas.", table_cell_style)
        ]
    ]

    t_modulos = Table(modulos_data, colWidths=[1.8*inch, 5.4*inch])
    t_modulos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_PRIMARY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#d3d3d3")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_modulos)
    story.append(Spacer(1, 12))

    # SECTION 2
    story.append(Paragraph("2. Interconexión e Integración de los Módulos", h1_style))
    story.append(Paragraph(
        "Ningún módulo opera de forma aislada. EduAgro conecta la información en tiempo real para reflejar la realidad del establecimiento:",
        body_style
    ))

    story.append(Paragraph("• <b>De Cosecha a Stock Físico:</b> Al cosechar un lote, se genera una Partida de Stock Físico en silobolsa o silo planta, registrando sus toneladas reales y humedad medida.", bullet_style))
    story.append(Paragraph("• <b>Subdivisión Estándar de Stock (1A/1B/1C):</b> El stock físico se divide dinámicamente en: <i>Stock Físico Real</i>, <i>Stock Reservado</i> (para cumplir contratos o pagar alquileres de campo), <i>Stock Asignado</i> (a viajes despachados) y <i>Stock Disponible Libre</i> (grano sin comprometer).", bullet_style))
    story.append(Paragraph("• <b>Clima + Stock Físico & Logística:</b> El pronóstico de lluvia a 72h evalúa la transitabilidad de caminos rurales, determinando si el grano en silobolsa puede ser retirado o si queda bloqueado por intransitabilidad de piso.", bullet_style))
    story.append(Paragraph("• <b>Mercado de Granos + Fletes $\\rightarrow$ Precio Neto en Origen:</b> Resta al precio ofrecido en puerto la tarifa de flete, el costo de secada y comisiones, calculando cuánto dinero le queda al productor por tonelada puesta en su campo.", bullet_style))
    story.append(Paragraph("• <b>Insumos + Productivo:</b> Al programar una pulverización o siembra, el sistema verifica que existan insumos suficientes en depósito antes de autorizar la orden de trabajo.", bullet_style))

    story.append(Spacer(1, 10))

    # SECTION 3
    story.append(Paragraph("3. Razonamiento del Agente Inteligente (Cómo calcula sus decisiones)", h1_style))
    story.append(Paragraph(
        "El Agente de EduAgro opera de forma <b>100% determinística y explicable</b>. No adivina ni usa modelos de texto impredecibles para calcular recomendaciones. El proceso de decisión sigue estos pasos:",
        body_style
    ))

    pasos_agente = [
        Paragraph("<b>Paso 1 - Consolidación del Contexto:</b> El agente reúne la foto completa de la empresa (humedad del grano, clima a 72h, precios spot/futuros, tarifas de flete, stock libre y contratos por vencer).", bullet_style),
        Paragraph("<b>Paso 2 - Ajuste de Umbrales (Política):</b> Aplica los parámetros preferidos por el productor o la zona agronómica (ej. umbral de viento para pulverización o prima mínima deseada en futuros).", bullet_style),
        Paragraph("<b>Paso 3 - Calculadoras Matemáticas Puramente Determinísticas:</b> Calcula el costo de secada, el precio neto en origen por destino, el desvío de balanza entre campo y puerto, y el pase de futuros (carry comercial).", bullet_style),
        Paragraph("<b>Paso 4 - Evaluación de Reglas de Negocio:</b> Contrasta los resultados contra el catálogo de reglas agronómicas, comerciales y logísticas.", bullet_style),
        Paragraph("<b>Paso 5 - Emisión de Recomendaciones Trazables:</b> Genera consejos prácticos ordenados por severidad (Crítica, Advertencia, Información, Éxito) indicando el motivo, las variables determinantes y la acción sugerida.", bullet_style),
    ]
    for p in pasos_agente:
        story.append(p)

    story.append(Spacer(1, 10))
    story.append(PageBreak())

    # SECTION 4
    story.append(Paragraph("4. Catálogo de Reglas y Escenarios del Agente", h1_style))
    story.append(Paragraph(
        "A continuación se detallan las reglas integradas en los módulos <code>comercial_rules.py</code> y <code>decision_rules</code>, "
        "explicando los umbrales de activación, los motivos y el razonamiento del agente en diferentes escenarios reales.",
        body_style
    ))

    # SUBSECTION 4.1: Comercial Rules
    story.append(Paragraph("4.1. Reglas del Agente Comercial (comercial_rules.py)", h2_style))

    reglas_comerciales_data = [
        [
            Paragraph("Código de Regla", table_header_style),
            Paragraph("Nivel", table_header_style),
            Paragraph("Umbral / Disparador", table_header_style),
            Paragraph("Razonamiento y Escenario del Agente", table_header_style)
        ],
        [
            Paragraph("<b>COBERTURA_BAJA</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Warning</b></font>", table_cell_style),
            Paragraph("Cobertura $< 25\%$ de la producción total.", table_cell_style),
            Paragraph("El productor tiene la mayor parte de su cosecha expuesta a la volatilidad de precios. El agente sugiere evaluar fijaciones o coberturas para defender el margen.", table_cell_style)
        ],
        [
            Paragraph("<b>COBERTURA_MEDIA</b>", table_cell_style),
            Paragraph("<b>Info</b>", table_cell_style),
            Paragraph("Cobertura entre $25\%$ y $60\%$.", table_cell_style),
            Paragraph("Posición comercial equilibrada. Existe un nivel de protección aceptable conservando volumen libre para capturar subas de mercado.", table_cell_style)
        ],
        [
            Paragraph("<b>COBERTURA_ALTA</b>", table_cell_style),
            Paragraph("<font color='#2d6a4f'><b>Success</b></font>", table_cell_style),
            Paragraph("Cobertura $\\ge 60\%$ de la cosecha.", table_cell_style),
            Paragraph("Posición fuertemente protegida contra caídas de mercado mediante ventas fijas y reservas comerciales firmes.", table_cell_style)
        ],
        [
            Paragraph("<b>EXPOSICION_A_FIJAR_ELEVADA</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Warning</b></font>", table_cell_style),
            Paragraph("Ventas 'A Fijar' $\\ge 15\%$ de la cosecha.", table_cell_style),
            Paragraph("Alerta que un volumen importante de granos ya fue entregado sin precio firme, estando expuesto a las variaciones de la Pizarra.", table_cell_style)
        ],
        [
            Paragraph("<b>CARGA_COMPROMISOS_ELEVADA</b>", table_cell_style),
            Paragraph("<b>Info</b>", table_cell_style),
            Paragraph("Compromisos por alquiler o insumos $\\ge 30\%$ de la producción.", table_cell_style),
            Paragraph("Identifica la porción de grano retenida para cancelar obligaciones contractuales que no aportará flujo de caja líquido neto.", table_cell_style)
        ],
        [
            Paragraph("<b>CONCENTRACION_SILO_BOLSA</b>", table_cell_style),
            Paragraph("<b>Info</b>", table_cell_style),
            Paragraph("Stock en silobolsa $\\ge 70\%$ del stock total.", table_cell_style),
            Paragraph("Alerta la alta concentración de existencias en el campo, recomendando controles periódicos de humedad y roturas de bolsa.", table_cell_style)
        ],
        [
            Paragraph("<b>VALORIZACION_STOCK_LIBRE</b>", table_cell_style),
            Paragraph("<font color='#2d6a4f'><b>Success</b></font>", table_cell_style),
            Paragraph("Valor de stock libre $\\ge \\mathrm{US\\$}\\ 10.000$.", table_cell_style),
            Paragraph("Informa el activo comercial líquido disponible estimado a la cotización Pizarra Rosario para oportuna toma de decisiones de venta.", table_cell_style)
        ]
    ]

    t_reglas_com = Table(reglas_comerciales_data, colWidths=[1.5*inch, 0.7*inch, 1.6*inch, 3.4*inch])
    t_reglas_com.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_SECONDARY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#d3d3d3")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_reglas_com)
    story.append(Spacer(1, 14))

    # SUBSECTION 4.2: Decision Engine Rules
    story.append(Paragraph("4.2. Reglas Agronómicas, Meteorológicas y Logísticas (decision_rules)", h2_style))

    reglas_decis_data = [
        [
            Paragraph("Código de Regla", table_header_style),
            Paragraph("Nivel", table_header_style),
            Paragraph("Escenario / Condición Disparadora", table_header_style),
            Paragraph("Conclusión del Agente y Recomendación Operativa", table_header_style)
        ],
        [
            Paragraph("<b>HUMEDAD_ALTA_Y_VENTANA_SECA</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Warning</b></font>", table_cell_style),
            Paragraph("Humedad de grano $>$ base commercial ($>14.5\%$ en maíz) AND lluvia a 72h $< 10\\ \\mathrm{mm}$.", table_cell_style),
            Paragraph("<b>Esperar secado natural en pie.</b> No hay riesgo inminente de lluvia y se evita pagar costo de secada ($\approx \\mathrm{US\\$}\\ 2.50/\\mathrm{Tn}/\\text{punto}$).", table_cell_style)
        ],
        [
            Paragraph("<b>HUMEDAD_ALTA_Y_LLUVIA_PROXIMA</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Danger</b></font>", table_cell_style),
            Paragraph("Humedad de grano $>$ base comercial AND lluvia a 72h $\\ge 10\\ \\mathrm{mm}$.", table_cell_style),
            Paragraph("<b>Cosechar e ingresar a secadora inmediatamente.</b> El riesgo de vuelco, brotado o pérdida de piso supera el costo económico de secar el grano.", table_cell_style)
        ],
        [
            Paragraph("<b>COSTO_SECADA_ELEVADO</b>", table_cell_style),
            Paragraph("<b>Info</b>", table_cell_style),
            Paragraph("Costo de secada $\\ge 3\\%$ del precio spot del grano.", table_cell_style),
            Paragraph("Alerta revisar la tabla tarifaria de mermas del acopio/puerto antes de enviar el camión.", table_cell_style)
        ],
        [
            Paragraph("<b>ALERTA_PULVERIZACION_VIENTO</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Danger / Info</b></font>", table_cell_style),
            Paragraph("Viento o ráfagas fuera del rango óptimo ($5-10\\ \\mathrm{km/h}$) o $> 15\\ \\mathrm{km/h}$.", table_cell_style),
            Paragraph("<b>Suspender o extremar precauciones.</b> Viento $>15\\ \\mathrm{km/h}$ provoca deriva de producto; viento $<5\\ \\mathrm{km/h}$ genera riesgo de inversión térmica.", table_cell_style)
        ],
        [
            Paragraph("<b>RIESGO_TERMICO_A_VERIFICAR</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Warning / Danger</b></font>", table_cell_style),
            Paragraph("Temperatura mínima a 72h $\\le 4.0^\\circ\\mathrm{C}$.", table_cell_style),
            Paragraph("Alerta preventivo por helada. Recomienda inspeccionar bajíos y estaciones agrometeorológicas según la etapa fenológica del cultivo.", table_cell_style)
        ],
        [
            Paragraph("<b>RIESGO_DE_PISO_POR_PRECIPITACION</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Warning / Danger</b></font>", table_cell_style),
            Paragraph("Lluvia proyectada a 72h $\\ge 10\\ \\mathrm{mm}$.", table_cell_style),
            Paragraph("Alerta pérdida de sustentación en caminos rurales de tierra. Puede bloquear el ingreso de cosechadoras y camiones al lote.", table_cell_style)
        ],
        [
            Paragraph("<b>DESTINO_NETO_MAS_CONVENIENTE</b>", table_cell_style),
            Paragraph("<font color='#2d6a4f'><b>Success</b></font>", table_cell_style),
            Paragraph("Comparación de destinos donde el más conveniente saca $\\ge \\mathrm{US\\$}\\ 1.00/\\mathrm{Tn}$ de ventaja.", table_cell_style),
            Paragraph("Recomienda el puerto o acopio con mayor <i>Precio Neto en Origen</i> (descontando flete y secada), detallando la ventaja económica por tonelada.", table_cell_style)
        ],
        [
            Paragraph("<b>DIFERENCIA_DE_PESAJE_A_REVISAR</b>", table_cell_style),
            Paragraph("<font color='#b7094c'><b>Danger</b></font>", table_cell_style),
            Paragraph("Diferencia balanza destino vs origen $> 1.0\\%$ o $> 300\\ \\mathrm{kg}$.", table_cell_style),
            Paragraph("Detiene la transacción y la envía a reconciliación explícita para auditar posibles mermas o pérdidas en el trayecto.", table_cell_style)
        ],
        [
            Paragraph("<b>FUTURO_FAVORABLE_PARA_FIJACION</b>", table_cell_style),
            Paragraph("<font color='#2d6a4f'><b>Success</b></font>", table_cell_style),
            Paragraph("Cotización a futuro Matba Rofex supera al spot por $\\ge \\mathrm{US\\$}\\ 4.00/\\mathrm{Tn}$.", table_cell_style),
            Paragraph("Recomienda analizar la cobertura a futuro comparando el pase bruto contra los costos de almacenaje e inmovilización financiera del grano.", table_cell_style)
        ]
    ]

    t_reglas_decis = Table(reglas_decis_data, colWidths=[1.6*inch, 0.8*inch, 1.8*inch, 3.0*inch])
    t_reglas_decis.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), COLOR_PRIMARY),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#d3d3d3")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, COLOR_LIGHT_BG]),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t_reglas_decis)

    story.append(Spacer(1, 15))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_PRIMARY, spaceBefore=10, spaceAfter=10))
    story.append(Paragraph("<b>EduAgro v2.0/v3.0</b> - Documento de Arquitectura Funcional y Reglas del Agente Inteligente.", subtitle_style))

    doc.build(story)
    print(f"PDF generado exitosamente en: {filename}")

if __name__ == "__main__":
    build_pdf()
