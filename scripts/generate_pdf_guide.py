#!/usr/bin/env python3
"""
Generador de PDF para la Guía de Usuario por Perfil de EduAgro ERP.
Explicación didáctica completa de cada módulo para usuarios no técnicos,
con capturas de pantalla apareadas y enlaces directos de acceso a la web app.
"""

import os
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, HRFlowable, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMG_DIR = os.path.join(BASE_DIR, "static", "img")
APP_URL = os.environ.get("APP_BASE_URL", "https://eduagro.ggsolutions.com.ar").rstrip("/")

def make_screenshot_flowable(img_filename, width=480, title="", caption="", link_url=""):
    img_path = os.path.join(IMG_DIR, img_filename)
    flowables = []

    if os.path.exists(img_path):
        try:
            from PIL import Image as PILImage
            with PILImage.open(img_path) as im:
                w, h = im.size
                aspect = h / float(w)
                target_h = width * aspect

            img = Image(img_path, width=width, height=target_h)
            flowables.append(Spacer(1, 4))
            flowables.append(img)
            
            caption_text = f"📷 <b>{title}</b> — {caption}" if title else f"📷 <i>{caption}</i>"
            if link_url:
                caption_text += f"<br/><a href='{link_url}' color='#15803d'><b><u>👉 Haz clic aquí para abrir esta sección en EduAgro ({link_url})</u></b></a>"

            cap_style = ParagraphStyle(
                'ImgCaption',
                fontName='Helvetica',
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#334155"),
                alignment=TA_CENTER,
                spaceBefore=5,
                spaceAfter=12
            )
            flowables.append(Paragraph(caption_text, cap_style))
        except Exception as e:
            print(f"Advertencia al procesar imagen {img_filename}: {e}")

    return flowables

def build_pdf(filename="Manual_Usuario_EduAgro.pdf"):
    pdf_output_path = os.path.join(BASE_DIR, filename)
    doc = SimpleDocTemplate(
        pdf_output_path,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()

    # Colores EduAgro
    VERDE_OSCURO = colors.HexColor("#15803d")
    VERDE_PRIMARIO = colors.HexColor("#166534")
    AMBAR = colors.HexColor("#d97706")
    SLATE_DARK = colors.HexColor("#0f172a")
    SLATE_LIGHT = colors.HexColor("#f8fafc")
    GREY_BORDER = colors.HexColor("#e2e8f0")

    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=VERDE_OSCURO,
        alignment=TA_CENTER,
        spaceAfter=8
    )

    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Oblique',
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#475569"),
        alignment=TA_CENTER,
        spaceAfter=14
    )

    h1_style = ParagraphStyle(
        'H1',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=15,
        leading=19,
        textColor=VERDE_PRIMARIO,
        spaceBefore=14,
        spaceAfter=6
    )

    h2_style = ParagraphStyle(
        'H2',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        leading=15,
        textColor=SLATE_DARK,
        spaceBefore=10,
        spaceAfter=4
    )

    body_style = ParagraphStyle(
        'Body',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9.5,
        leading=13.5,
        textColor=SLATE_DARK,
        spaceAfter=8,
        alignment=TA_LEFT
    )

    callout_style = ParagraphStyle(
        'Callout',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=3,
        spaceAfter=3
    )

    table_header_style = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
        textColor=colors.white,
        alignment=TA_CENTER
    )

    table_body_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8.5,
        leading=11.5,
        textColor=SLATE_DARK
    )

    elements = []

    # -------------------------------------------------------------------------
    # PORTADA Y EXPLICACIÓN GENERAL
    # -------------------------------------------------------------------------
    elements.append(Paragraph("🌾 <b>Manual de Usuario EduAgro ERP</b>", title_style))
    elements.append(Paragraph("Guía Didáctica Módulo por Módulo con Capturas de Pantalla y Enlaces Directos<br/><i>Para la Empresa Agropecuaria Familiar de Córdoba</i>", subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=VERDE_OSCURO, spaceBefore=4, spaceAfter=12))

    intro_p = ("<b>¿Qué es EduAgro?</b> EduAgro es el software que une el trabajo del campo ('sobre la camioneta') con "
               "la administración de la oficina. Organiza en un solo lugar la información de lotes, siembras, lluvias, "
               "stock de granos, ventas y facturas de servicios rurales.<br/>"
               "🌐 <b>Plataforma Web Activa:</b> Se puede ingresar en todo momento desde el navegador en "
               f"<a href='{APP_URL}' color='#15803d'><b><u>{APP_URL}</u></b></a>")
    elements.append(Paragraph(intro_p, body_style))
    elements.append(Spacer(1, 8))

    # -------------------------------------------------------------------------
    # TABLA DE MÓDULOS Y NAVEGACIÓN
    # -------------------------------------------------------------------------
    elements.append(Paragraph("<b>Módulos del Sistema y Enlaces Directos</b>", h2_style))
    
    data_table = [
        [
            Paragraph("Módulo del Sistema", table_header_style),
            Paragraph("¿Para qué sirve? (Objetivo)", table_header_style),
            Paragraph("Enlace Directo en Navegador", table_header_style)
        ],
        [
            Paragraph("<b>🏠 Portal de Entrada</b>", table_body_style),
            Paragraph("Patio principal: resumen del campo, cotizaciones y menú.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/' color='#15803d'><b><u>Abrir Portal ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>🌾 Lotes & Siembras</b>", table_body_style),
            Paragraph("Pizarra de hectáreas, cultivos sembrados y rindes.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/productivo/lotes' color='#15803d'><b><u>Abrir Lotes ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>🌤️ Clima & Lluvias</b>", table_body_style),
            Paragraph("Pronóstico a 72 hs y extendido a 14 días.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/clima/campos' color='#15803d'><b><u>Abrir Clima ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>🚜 Modo Campo</b>", table_body_style),
            Paragraph("Pantalla táctil celular para carga de lluvia y trabajos.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/campo' color='#15803d'><b><u>Abrir Modo Campo ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>📈 Comercialización</b>", table_body_style),
            Paragraph("Cotización Pizarra Rosario (BCR), stock y contratos.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/comercial' color='#15803d'><b><u>Abrir Comercial ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>⚡ Servicios Rurales</b>", table_body_style),
            Paragraph("Semáforo de facturas (EPEC, impuestos, patentes).", table_body_style),
            Paragraph(f"<a href='{APP_URL}/servicios/campos' color='#15803d'><b><u>Abrir Servicios ↗</u></b></a>", table_body_style)
        ]
    ]

    t = Table(data_table, colWidths=[130, 250, 140])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), VERDE_PRIMARIO),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, SLATE_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 10))

    # -------------------------------------------------------------------------
    # DETALLE DE CADA MÓDULO CON SUS CAPTURAS EXACTAS
    # -------------------------------------------------------------------------

    # SECCIÓN 1: PORTAL DE ENTRADA (dashboard.png)
    elements.append(Paragraph("1. Portal de Entrada Principal (dashboard.png)", h1_style))
    p_dash = ("<b>¿Para qué sirve esta pantalla?</b> Es el 'patio de entrada' del establecimiento. "
              "Permite visualizar de un vistazo la superficie total trabajada, la cotización de pizarra del dólar divisa, "
              "el clima actual y los botones de acceso directo para ingresar a cada módulo según la tarea del día.<br/>"
              "<b>¿Cómo se usa?</b> Al abrir la aplicación, el usuario puede revisar las cotizaciones antes de vender o presionar "
              "el módulo al que desea ingresar.")
    elements.append(Paragraph(p_dash, body_style))
    elements.extend(make_screenshot_flowable("dashboard.png", width=470, title="dashboard.png", caption="Portal de Entrada Principal y Centro de Operaciones del Establecimiento", link_url=f"{APP_URL}/"))

    # SECCIÓN 2: PRODUCTIVO - CAMPOS (productivo_campos.png)
    elements.append(Paragraph("2. Módulo Productivo: Campos y Establecimientos (productivo_campos.png)", h1_style))
    p_campos = ("<b>¿Para qué sirve esta pantalla?</b> Organiza la superficie rural total del establecimiento. "
                "Diferencia las hectáreas que son de propiedad familiar de las hectáreas alquiladas a terceros (arrendamiento), "
                "calculando la superficie productiva nula y los costos de alquiler.<br/>"
                "<b>¿Cómo se usa?</b> Se hace clic en 'Nuevo Campo' para dar de alta una finca o seleccionar un campo existente "
                "para revisar su ubicación en Córdoba y hectáreas totales.")
    elements.append(Paragraph(p_campos, body_style))
    elements.extend(make_screenshot_flowable("productivo_campos.png", width=470, title="productivo_campos.png", caption="Resumen de Campos, Tenencia (Propio/Alquilado) y Hectáreas Totales", link_url=f"{APP_URL}/productivo/campos"))

    # SECCIÓN 3: PRODUCTIVO - LOTES (productivo_lotes.png)
    elements.append(Paragraph("3. Módulo Productivo: Pizarra de Lotes y Cultivos (productivo_lotes.png)", h1_style))
    p_lotes = ("<b>¿Para qué sirve esta pantalla?</b> Es la tarjeta de cultivo de cada cuadro del campo. Muestra qué cultivo está sembrado "
               "(Soja 1ra, Trigo, Maíz), la etapa de crecimiento y los rindes estimados en Quintales por Hectárea (qq/ha).<br/>"
               "<b>¿Cómo se usa?</b> El productor hace clic sobre la tarjeta de un lote para cargar el rinde estimado o ingresar el rinde real de cosecha.")
    elements.append(Paragraph(p_lotes, body_style))

    tip_lotes = [
        [Paragraph("🌾 <b>Regla Frecuente de Campo:</b> 10 Quintales (qq) equivalen exactamente a 1 Tonelada (Tn). Ejemplo: 35 qq/ha en 100 ha equivalen a 350 Toneladas totales.", callout_style)]
    ]
    t_tip_lotes = Table(tip_lotes, colWidths=[510])
    t_tip_lotes.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#fef3c7")),
        ('BORDER', (0,0), (-1,-1), 1, colors.HexColor("#fde68a")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_tip_lotes)
    elements.extend(make_screenshot_flowable("productivo_lotes.png", width=470, title="productivo_lotes.png", caption="Pizarra Visual por Lote, Estado del Cultivo y Rindes en Quintales", link_url=f"{APP_URL}/productivo/lotes"))

    # SECCIÓN 4: CLIMA (clima.png)
    elements.append(Paragraph("4. Módulo Agrometeorología & Clima (clima.png)", h1_style))
    p_clima = ("<b>¿Para qué sirve esta pantalla?</b> Brinda información meteorológica precisa del campo. "
               "Incluye serie horaria a 72 horas y pronóstico extendido a 14 días con porcentaje de probabilidad de precipitaciones.<br/>"
               "<b>¿Cómo se usa?</b> Se consulta antes de realizar labores de pulverización, fertilización o siembra para verificar condiciones del viento y lluvia.")
    elements.append(Paragraph(p_clima, body_style))
    elements.extend(make_screenshot_flowable("clima.png", width=470, title="clima.png", caption="Pronóstico Agrometeorológico de Temperatura, Viento y Probabilidad de Lluvia", link_url=f"{APP_URL}/clima/campos"))

    # SECCIÓN 5: MODO CAMPO (campo.png)
    elements.append(Paragraph("5. Modo Campo Rápido en Celular (campo.png)", h1_style))
    p_campo = ("<b>¿Para qué sirve esta pantalla?</b> Es la versión táctil diseñada para teléfonos celulares y tablets. "
               "Permite al encargado o tractorista registrar lluvias en milímetros (mm) o anotar observaciones con botones grandes sin complicaciones.<br/>"
               "<b>¿Cómo se usa?</b> Al salir a recorrer los lotes, abre esta pantalla en el celular, presiona los botones de lluvia (+5mm, +10mm) y toca Guardar. "
               "Funciona sin señal de celular guardando los datos offline en la memoria del teléfono.")
    elements.append(Paragraph(p_campo, body_style))
    elements.extend(make_screenshot_flowable("campo.png", width=380, title="campo.png", caption="Interfaz Táctil Modo Campo para Uso sobre la Camioneta (Offline)", link_url=f"{APP_URL}/campo"))

    # SECCIÓN 6: COMERCIALIZACIÓN - RESUMEN (comercial.png y comercial_tabla.png)
    elements.append(Paragraph("6. Módulo Comercialización: Mercado & Pizarra (comercial.png y comercial_tabla.png)", h1_style))
    p_com = ("<b>¿Para qué sirve esta pantalla?</b> Informa diariamente las cotizaciones Spot de Pizarra Rosario (Cámara Arbitral de Cereales - BCR) "
             "en Dólares por Tonelada (US$/Tn) y Pesos ($ARS/Tn), junto a la tasa oficial del Dólar Divisa Banco Nación (BNA).<br/>"
             "<b>¿Cómo se usa?</b> El usuario elige entre Soja, Maíz o Trigo para saber exactamente cuánto vale hoy su grano cosechado y valorizar su cereal disponible.")
    elements.append(Paragraph(p_com, body_style))
    elements.extend(make_screenshot_flowable("comercial.png", width=470, title="comercial.png", caption="Resumen Posición Comercial de Granos y Valorización de Stock Libre", link_url=f"{APP_URL}/comercial"))
    elements.extend(make_screenshot_flowable("comercial_tabla.png", width=470, title="comercial_tabla.png", caption="Tabla Snapshot de Cotizaciones en Vivo por Cultivo y Dólar BNA", link_url=f"{APP_URL}/comercial"))

    # SECCIÓN 7: STOCK FÍSICO (stock.png)
    elements.append(Paragraph("7. Módulo Comercialización: Stock Físico en Silobolsa y Acopio (stock.png)", h1_style))
    p_stock = ("<b>¿Para qué sirve esta pantalla?</b> Lleva la cuenta exacta del grano cosechado y guardado. "
               "Diferencia las Toneladas en mangas o silobolsas en el campo de las Toneladas en acopios o puerto.<br/>"
               "<b>¿Cómo se usa?</b> Permite registrar cada silobolsa armada durante la cosecha para controlar las reservas reales antes de vender.")
    elements.append(Paragraph(p_stock, body_style))
    elements.extend(make_screenshot_flowable("stock.png", width=470, title="stock.png", caption="Control de Toneladas Almacenadas en Silobolsa y Acopios de Terceros", link_url=f"{APP_URL}/comercial/stock"))

    # SECCIÓN 8: CONTRATOS Y COMPROMISOS (contratos-compromisos.png)
    elements.append(Paragraph("8. Módulo Comercialización: Contratos & Ventas (contratos-compromisos.png)", h1_style))
    p_con = ("<b>¿Para qué sirve esta pantalla?</b> Administra los compromisos de entrega de grano celebrados con corredores o acopios:<br/>"
             "• <b>Precio Fijo (Verde):</b> Ventas con precio en dólares ya cerrado.<br/>"
             "• <b>Precio A Fijar (Azul):</b> Grano entregado en acopio pendiente de poner precio.<br/>"
             "• <b>Canje Agropecuario (Naranja):</b> Granos comprometidos para pagar semillas, fertilizantes o alquileres.<br/>"
             "<b>¿Cómo se usa?</b> Registra los contratos celebrados para saber cuántas toneladas faltan entregar o fijar precio.")
    elements.append(Paragraph(p_con, body_style))
    elements.extend(make_screenshot_flowable("contratos-compromisos.png", width=470, title="contratos-compromisos.png", caption="Listado de Contratos Clasificados (Precio Fijo, A Fijar y Canje)", link_url=f"{APP_URL}/comercial/contratos"))

    # SECCIÓN 9: MOTOR DE DECISIONES COMERCIAL (comercial_agente-decisiones.png)
    elements.append(Paragraph("9. Motor de Recomendaciones y Decisiones Comercial (comercial_agente-decisiones.png)", h1_style))
    p_dec = ("<b>¿Para qué sirve esta pantalla?</b> Asistente inteligente que calcula automáticamente las mermas por humedad "
             "y el costo de secado en planta vs. vender en disponible o fijar contratos a futuro en Matba Rofex.<br/>"
             "<b>¿Cómo se usa?</b> Ingrese el porcentaje de humedad del grano cosechado y la herramienta le sugerirá si conviene guardar en silobolsa o entregar directo a puerto.")
    elements.append(Paragraph(p_dec, body_style))
    elements.extend(make_screenshot_flowable("comercial_agente-decisiones.png", width=470, title="comercial_agente-decisiones.png", caption="Calculador Inteligente de Mermas por Humedad y Decisiones de Venta", link_url=f"{APP_URL}/comercial"))

    # SECCIÓN 10: SERVICIOS RURALES (servicios.png)
    elements.append(Paragraph("10. Módulo Servicios Rurales e Instalaciones (servicios.png)", h1_style))
    p_serv = ("<b>¿Para qué sirve esta pantalla?</b> Lleva el control financiero de facturas y vencimientos rurales:<br/>"
              "• 🟢 <b>Al día:</b> Factura pagada.<br/>"
              "• 🟡 <b>Próximo Vencer:</b> Vence en los próximos días.<br/>"
              "• 🔴 <b>Vencido:</b> Requiere pago inmediato.<br/>"
              "Aplica para Luz Rural EPEC, internet satelital, patentes de vehículos, combustible e impuestos municipales.<br/>"
              "<b>¿Cómo se usa?</b> Revise el semáforo semanalmente para evitar cortes de servicios en el establecimiento.")
    elements.append(Paragraph(p_serv, body_style))
    elements.extend(make_screenshot_flowable("servicios.png", width=470, title="servicios.png", caption="Semáforo de Pagos de Servicios Rurales (EPEC, Combustible e Impuestos)", link_url=f"{APP_URL}/servicios/campos"))

    # SECCIÓN 11: GUÍA PASO A PASO - ¿CÓMO COMENZAR A USAR EDUAGRO?
    elements.append(Paragraph("11. Guía Paso a Paso: ¿Cómo comenzar a usar EduAgro en tu Campo?", h1_style))
    
    p_comienzo_intro = ("<b>Recomendaciones para configurar tu establecimiento desde cero:</b><br/>"
                        "Para aprovechar al máximo EduAgro y sacarle el jugo al sistema desde el primer día, "
                        "te sugerimos seguir este orden sencillo de trabajo:")
    elements.append(Paragraph(p_comienzo_intro, body_style))

    pasos_data = [
        [
            Paragraph("Paso", table_header_style),
            Paragraph("Acción a Realizar", table_header_style),
            Paragraph("¿Dónde se hace en la App?", table_header_style)
        ],
        [
            Paragraph("<b>Paso 1</b>", table_body_style),
            Paragraph("<b>Crear tu Campo / Finca:</b><br/>Ingresa el nombre de tu campo, superficie total en hectáreas y si es Propio o Alquilado.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/productivo/campos' color='#15803d'><b><u>1. Módulo Campos ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>Paso 2</b>", table_body_style),
            Paragraph("<b>Dividir y Cargar tus Lotes:</b><br/>Crea cada cuadro o lote con su nombre, hectáreas productivas, tipo de suelo y cultivo actual (Soja, Trigo, Maíz).", table_body_style),
            Paragraph(f"<a href='{APP_URL}/productivo/lotes' color='#15803d'><b><u>2. Módulo Lotes ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>Paso 3</b>", table_body_style),
            Paragraph("<b>Cargar Instalaciones y Servicios:</b><br/>Vincula las bombas de agua, casas o galpones y agrega las facturas de Luz Rural (EPEC), patentes e impuestos.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/servicios/campos' color='#15803d'><b><u>3. Módulo Servicios ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>Paso 4</b>", table_body_style),
            Paragraph("<b>Cargar Lluvias y Labores ('Modo Campo'):</b><br/>Instala el acceso al celular y empieza a anotar las lluvias del pluviómetro y tareas del día.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/campo' color='#15803d'><b><u>4. Modo Campo ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>Paso 5</b>", table_body_style),
            Paragraph("<b>'Jugar' con los Estados del Campo:</b><br/>A medida que avance la campaña, cambia el estado del lote (Barbecho ➔ Sembrado ➔ En Crecimiento ➔ Cosechado) y registra los rindes obtenidos.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/productivo/lotes' color='#15803d'><b><u>5. Módulo Lotes ↗</u></b></a>", table_body_style)
        ],
        [
            Paragraph("<b>Paso 6</b>", table_body_style),
            Paragraph("<b>Cargar Silobolsas y Vender Granos:</b><br/>Al cosechar, registra el stock en silobolsas, consulta la pizarra de precios BCR y carga tus contratos a fijar o de canje.", table_body_style),
            Paragraph(f"<a href='{APP_URL}/comercial' color='#15803d'><b><u>6. Comercialización ↗</u></b></a>", table_body_style)
        ]
    ]

    t_pasos = Table(pasos_data, colWidths=[55, 335, 130])
    t_pasos.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), VERDE_PRIMARIO),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('VALIGN', (0,0), (-1,-1), 'TOP'),
        ('GRID', (0,0), (-1,-1), 0.5, GREY_BORDER),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, SLATE_LIGHT]),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
    ]))
    elements.append(t_pasos)

    # Pie final
    elements.append(Spacer(1, 15))
    elements.append(HRFlowable(width="100%", thickness=1, color=GREY_BORDER, spaceBefore=10, spaceAfter=10))
    elements.append(Paragraph("<font size=8 color='#94a3b8'>EduAgro ERP - Documentación Oficial Didáctica - Córdoba, Argentina - 2026</font>", ParagraphStyle('Foot', alignment=TA_CENTER)))

    doc.build(elements)
    print(f"✅ Manual PDF interactivo generado exitosamente en: {pdf_output_path}")

if __name__ == "__main__":
    build_pdf()
