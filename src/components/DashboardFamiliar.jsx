import React, { useState } from 'react';
import {
  TrendingUp,
  CloudRain,
  DollarSign,
  Wheat,
  Calendar,
  CheckCircle2,
  AlertCircle,
  FileText,
  Eye,
  Filter,
  ArrowUpRight,
  ArrowDownRight,
  Building2,
  Users,
  Sprout,
  ShieldAlert,
  ChevronDown,
  X,
  CreditCard,
  Layers,
  Sparkles
} from 'lucide-react';

export default function DashboardFamiliar() {
  // ---------------------------------------------------------------------------
  // Estado Global del Dashboard
  // ---------------------------------------------------------------------------
  const [perfilVista, setPerfilVista] = useState('dueno'); // 'dueno' | 'finanzas' | 'campo'
  const [modalComprobante, setModalComprobante] = useState(null);
  const [toastMsg, setToastMsg] = useState(null);

  // Cotización Dolar Oficial / Canje Agro
  const cotizacionDolar = 1285.50;

  // Lista de Vencimientos e Impuestos Rurales
  const [vencimientos, setVencimientos] = useState([
    {
      id: 1,
      concepto: 'EPEC - Luz Rural (Bombas Lote 2)',
      categoria: 'Servicios',
      montoArs: 485000,
      montoUsd: 377.28,
      fechaVencimiento: '2026-08-02',
      estado: 'vencido', // 'pendiente' | 'pagado' | 'vencido'
      comprobanteUrl: 'https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80',
    },
    {
      id: 2,
      concepto: 'Arrendamiento Campo San José (Cuota 2/4)',
      categoria: 'Arrendamiento',
      montoArs: 3850000,
      montoUsd: 2994.94,
      fechaVencimiento: '2026-08-10',
      estado: 'pendiente',
      comprobanteUrl: 'https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=600&q=80',
    },
    {
      id: 3,
      concepto: 'Impuesto Inmobiliario Rural Córdoba (Cuota 4)',
      categoria: 'Impuestos',
      montoArs: 620000,
      montoUsd: 482.30,
      fechaVencimiento: '2026-08-15',
      estado: 'pendiente',
      comprobanteUrl: 'https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?auto=format&fit=crop&w=600&q=80',
    },
    {
      id: 4,
      concepto: 'Seguro Granizo Sancor Seguros (Soja 1ra)',
      categoria: 'Seguros',
      montoArs: 1250000,
      montoUsd: 972.38,
      fechaVencimiento: '2026-07-20',
      estado: 'pagado',
      comprobanteUrl: 'https://images.unsplash.com/photo-1450133064473-71024230f91b?auto=format&fit=crop&w=600&q=80',
    },
  ]);

  // Datos para Gráfico de Rendimiento por Lote (Inversión vs Retorno USD/ha)
  const lotesRendimiento = [
    { lote: 'Lote 1 - El Norte', inversion: 420, retorno: 980, cultivo: 'Soja 1ra', ha: 145 },
    { lote: 'Lote 2 - La Lagunita', inversion: 510, retorno: 1150, cultivo: 'Trigo / Soja 2da', ha: 220 },
    { lote: 'Lote 3 - San José', inversion: 380, retorno: 820, cultivo: 'Soja 1ra', ha: 90 },
    { lote: 'Lote 4 - El Molino', inversion: 490, retorno: 1040, cultivo: 'Maíz Tardío', ha: 310 },
  ];

  const maxUSD = 1200; // Para escala del gráfico SVG

  const triggerToast = (msg) => {
    setToastMsg(msg);
    setTimeout(() => setToastMsg(null), 3500);
  };

  const handleMarcarPagado = (id) => {
    setVencimientos(
      vencimientos.map((item) =>
        item.id === id ? { ...item, estado: 'pagado' } : item
      )
    );
    const item = vencimientos.find((v) => v.id === id);
    triggerToast(`✓ Vencimiento "${item?.concepto}" marcado como PAGADO`);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 font-sans antialiased p-4 sm:p-6 lg:p-8 selection:bg-emerald-500 selection:text-slate-950">
      <div className="max-w-7xl mx-auto space-y-6">
        
        {/* =================================================================== */}
        {/* HEADER SUPERIOR & FILTRO DE PERFIL FAMILIAR                        */}
        {/* =================================================================== */}
        <header className="bg-slate-900/90 border border-slate-800 rounded-3xl p-5 shadow-2xl backdrop-blur flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center space-x-4">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-tr from-emerald-600 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-900/30">
              <Sprout className="w-7 h-7 text-slate-950 stroke-[2.5]" />
            </div>
            <div>
              <div className="flex items-center space-x-3">
                <h1 className="text-2xl sm:text-3xl font-black tracking-tight text-white">
                  Estancia El Mimbre <span className="text-emerald-400 text-lg font-normal">ERP Cordobés</span>
                </h1>
                <span className="hidden sm:inline-block px-3 py-1 bg-emerald-950 text-emerald-400 border border-emerald-800 text-xs font-semibold rounded-full">
                  Campaña 2025-2026
                </span>
              </div>
              <p className="text-xs sm:text-sm text-slate-400 mt-0.5">
                Panel de Control Familiar • Dólar Oficial/Canje: <strong className="text-emerald-400">${cotizacionDolar.toFixed(2)} ARS</strong>
              </p>
            </div>
          </div>

          {/* 1. FILTRO DE PERFIL SUPERIOR */}
          <div className="flex items-center space-x-3 bg-slate-950 p-1.5 rounded-2xl border border-slate-800 w-full md:w-auto">
            <Filter className="w-4 h-4 text-emerald-400 ml-2 hidden sm:inline" />
            <span className="text-xs font-bold text-slate-400 uppercase hidden sm:inline">Vista:</span>
            <div className="grid grid-cols-3 gap-1 w-full md:w-auto">
              {[
                { id: 'dueno', label: '👑 Vista Dueño' },
                { id: 'finanzas', label: '📊 Vista Finanzas' },
                { id: 'campo', label: '🚜 Vista Campo' },
              ].map((perfil) => (
                <button
                  key={perfil.id}
                  onClick={() => setPerfilVista(perfil.id)}
                  className={`px-3 py-2 rounded-xl text-xs font-bold transition-all ${
                    perfilVista === perfil.id
                      ? 'bg-emerald-600 text-slate-950 shadow-md shadow-emerald-600/30 font-black'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-900'
                  }`}
                >
                  {perfil.label}
                </button>
              ))}
            </div>
          </div>
        </header>

        {/* NOTIFICACIÓN TOAST */}
        {toastMsg && (
          <div className="fixed bottom-6 right-6 z-50 bg-emerald-950 border border-emerald-700 text-emerald-200 px-5 py-3.5 rounded-2xl shadow-2xl flex items-center space-x-3 animate-bounce">
            <CheckCircle2 className="w-5 h-5 text-emerald-400" />
            <span className="text-sm font-semibold">{toastMsg}</span>
          </div>
        )}

        {/* =================================================================== */}
        {/* 2. TARJETAS KPI PRINCIPALES                                        */}
        {/* =================================================================== */}
        <section className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          
          {/* KPI 1: HECTÁREAS SEMBRADAS */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-5 shadow-xl hover:border-emerald-500/40 transition-all relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-emerald-500/5 rounded-full blur-2xl group-hover:bg-emerald-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
              <span>Superficie Sembrada</span>
              <div className="p-2 rounded-xl bg-emerald-500/10 text-emerald-400">
                <Wheat className="w-5 h-5" />
              </div>
            </div>
            <div className="text-3xl font-black text-white tracking-tight mb-1">
              765 <span className="text-lg font-normal text-slate-400">ha</span>
            </div>
            <div className="space-y-1.5 mt-3 pt-3 border-t border-slate-800/80 text-xs">
              <div className="flex justify-between items-center text-slate-300">
                <span className="flex items-center gap-1.5 font-medium">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-400" /> Soja (1ra + 2da)
                </span>
                <span className="font-bold text-white">455 ha (59%)</span>
              </div>
              <div className="flex justify-between items-center text-slate-300">
                <span className="flex items-center gap-1.5 font-medium">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-400" /> Trigo (Invierno)
                </span>
                <span className="font-bold text-white">310 ha (41%)</span>
              </div>
            </div>
          </div>

          {/* KPI 2: LLUVIA ACUMULADA DEL MES */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-5 shadow-xl hover:border-cyan-500/40 transition-all relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-cyan-500/5 rounded-full blur-2xl group-hover:bg-cyan-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
              <span>Lluvia Mes (Julio)</span>
              <div className="p-2 rounded-xl bg-cyan-500/10 text-cyan-400">
                <CloudRain className="w-5 h-5" />
              </div>
            </div>
            <div className="text-3xl font-black text-white tracking-tight mb-1">
              84.5 <span className="text-lg font-normal text-cyan-400">mm</span>
            </div>
            <p className="text-xs text-slate-400 mt-2 flex items-center gap-1">
              <ArrowUpRight className="w-4 h-4 text-emerald-400 inline" />
              <strong className="text-emerald-400">+12%</strong> vs. promedio histórico Córdoba
            </p>
            <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] text-slate-400 flex justify-between">
              <span>Última precipitación:</span>
              <strong className="text-slate-200">22.0 mm (Hace 4 días)</strong>
            </div>
          </div>

          {/* KPI 3: GASTOS & SERVICIOS VENCIDOS */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-5 shadow-xl hover:border-amber-500/40 transition-all relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-amber-500/5 rounded-full blur-2xl group-hover:bg-amber-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
              <span>Servicios Vencidos / Por Vencer</span>
              <div className="p-2 rounded-xl bg-amber-500/10 text-amber-400">
                <CreditCard className="w-5 h-5" />
              </div>
            </div>
            <div className="text-3xl font-black text-amber-400 tracking-tight mb-1">
              $3,854.52 <span className="text-xs font-normal text-slate-400">USD</span>
            </div>
            <div className="text-xs font-semibold text-slate-300">
              ≈ ${(3854.52 * cotizacionDolar).toLocaleString('es-AR', { maximumFractionDigits: 0 })} ARS
            </div>
            <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] flex justify-between items-center text-amber-300">
              <span className="flex items-center gap-1 font-bold">
                <ShieldAlert className="w-3.5 h-3.5 text-amber-400" /> 1 Vencido
              </span>
              <span className="text-slate-400">2 por vencer este mes</span>
            </div>
          </div>

          {/* KPI 4: TONELADAS ESTIMADAS COSECHA */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-3xl p-5 shadow-xl hover:border-purple-500/40 transition-all relative overflow-hidden group">
            <div className="absolute top-0 right-0 w-24 h-24 bg-purple-500/5 rounded-full blur-2xl group-hover:bg-purple-500/10 transition-all" />
            <div className="flex items-center justify-between text-slate-400 text-xs font-bold uppercase tracking-wider mb-2">
              <span>Cosecha Estimada (Rinde)</span>
              <div className="p-2 rounded-xl bg-purple-500/10 text-purple-400">
                <TrendingUp className="w-5 h-5" />
              </div>
            </div>
            <div className="text-3xl font-black text-white tracking-tight mb-1">
              2,840 <span className="text-lg font-normal text-purple-400">t</span>
            </div>
            <div className="text-xs text-slate-400">
              Rinde Promedio: <strong className="text-slate-200">37.1 qq/ha</strong> (3.7 t/ha)
            </div>
            <div className="mt-3 pt-2 border-t border-slate-800/80 text-[11px] text-purple-300 flex justify-between">
              <span>Proyección Ingresos:</span>
              <strong className="text-emerald-400 font-bold">$924,000 USD</strong>
            </div>
          </div>

        </section>

        {/* =================================================================== */}
        {/* CONTENIDO PRINCIPAL EN 2 COLUMNAS (TABLA + GRÁFICO)               */}
        {/* =================================================================== */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">

          {/* 3. TABLA DE VENCIMIENTOS E IMPUESTOS RURALES (8 COLS) */}
          <section className="lg:col-span-7 bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-5">
                <div>
                  <h2 className="text-lg font-black text-white flex items-center gap-2">
                    <Building2 className="w-5 h-5 text-emerald-400" />
                    Vencimientos e Impuestos Rurales
                  </h2>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Servicios, patentes, luz rural y arrendamientos de campos cordobeses
                  </p>
                </div>
                <span className="text-xs font-bold bg-slate-800 px-3 py-1.5 rounded-xl text-slate-300 border border-slate-700">
                  {vencimientos.filter((v) => v.estado !== 'pagado').length} pendientes
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-300">
                  <thead className="bg-slate-950 text-slate-400 font-bold uppercase tracking-wider text-[10px] border-b border-slate-800">
                    <tr>
                      <th className="py-3 px-3">Concepto</th>
                      <th className="py-3 px-3">Vencimiento</th>
                      <th className="py-3 px-3 text-right">Monto ($ARS / $USD)</th>
                      <th className="py-3 px-3 text-center">Estado</th>
                      <th className="py-3 px-3 text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-medium">
                    {vencimientos.map((item) => (
                      <tr key={item.id} className="hover:bg-slate-800/40 transition-colors">
                        <td className="py-3.5 px-3">
                          <span className="block font-bold text-slate-100 text-sm">{item.concepto}</span>
                          <span className="text-[11px] text-slate-400">{item.categoria}</span>
                        </td>
                        <td className="py-3.5 px-3 whitespace-nowrap">
                          <span className="block text-slate-200 font-semibold">{item.fechaVencimiento}</span>
                        </td>
                        <td className="py-3.5 px-3 text-right whitespace-nowrap">
                          <span className="block font-bold text-slate-100">
                            ${item.montoArs.toLocaleString('es-AR')} ARS
                          </span>
                          <span className="text-[11px] text-emerald-400 font-semibold">
                            ${item.montoUsd.toFixed(2)} USD
                          </span>
                        </td>
                        <td className="py-3.5 px-3 text-center whitespace-nowrap">
                          {item.estado === 'pagado' && (
                            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-800">
                              ✓ Pagado
                            </span>
                          )}
                          {item.estado === 'pendiente' && (
                            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-amber-950 text-amber-300 border border-amber-800">
                              ⌛ Pendiente
                            </span>
                          )}
                          {item.estado === 'vencido' && (
                            <span className="px-2.5 py-1 rounded-full text-[10px] font-bold bg-red-950 text-red-400 border border-red-800 animate-pulse">
                              ⚠️ Vencido
                            </span>
                          )}
                        </td>
                        <td className="py-3.5 px-3 text-right whitespace-nowrap space-x-1.5">
                          {item.estado !== 'pagado' && (
                            <button
                              onClick={() => handleMarcarPagado(item.id)}
                              className="px-2.5 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-slate-950 font-extrabold text-[11px] transition-all shadow-md active:scale-95"
                              title="Marcar este servicio como pagado"
                            >
                              Pagar
                            </button>
                          )}
                          <button
                            onClick={() => setModalComprobante(item)}
                            className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all inline-flex items-center"
                            title="Ver Comprobante Adjunto"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-4 pt-4 border-t border-slate-800 flex justify-between items-center text-xs text-slate-400">
              <span>Demostración ERP Córdoba (Integración LPG y AFIP/ARCA)</span>
              <span className="text-emerald-400 font-semibold hover:underline cursor-pointer">
                Ver todos los vencimientos →
              </span>
            </div>
          </section>

          {/* 4. GRÁFICO DE RENDIMIENTO POR LOTE (INVERSIÓN VS RETORNO USD/HA) (5 COLS) */}
          <section className="lg:col-span-5 bg-slate-900/90 border border-slate-800 rounded-3xl p-6 shadow-2xl flex flex-col justify-between">
            <div>
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-lg font-black text-white flex items-center gap-2">
                  <TrendingUp className="w-5 h-5 text-emerald-400" />
                  Rendimiento por Lote ($USD/ha$)
                </h2>
              </div>
              <p className="text-xs text-slate-400 mb-6">
                Comparativo de Inversión Agronómica vs. Retorno Estimado por Hectárea
              </p>

              {/* Gráficos de Barras Personalizados en SVG / CSS Grid */}
              <div className="space-y-5">
                {lotesRendimiento.map((lote, index) => {
                  const pctInversion = (lote.inversion / maxUSD) * 100;
                  const pctRetorno = (lote.retorno / maxUSD) * 100;
                  const gananciaNeta = lote.retorno - lote.inversion;

                  return (
                    <div key={index} className="space-y-1.5">
                      <div className="flex justify-between items-center text-xs">
                        <span className="font-bold text-slate-100">{lote.lote}</span>
                        <span className="text-[11px] text-slate-400 font-medium">
                          Margen: <strong className="text-emerald-400">${gananciaNeta} USD/ha</strong>
                        </span>
                      </div>

                      {/* Barra Inversión vs Retorno */}
                      <div className="space-y-1 bg-slate-950 p-2 rounded-2xl border border-slate-800/80">
                        {/* Inversión */}
                        <div className="flex items-center text-[10px] space-x-2">
                          <span className="w-16 text-slate-400 font-semibold text-right">Inversión:</span>
                          <div className="flex-1 bg-slate-900 rounded-full h-3 overflow-hidden p-0.5">
                            <div
                              className="bg-gradient-to-r from-amber-500 to-orange-400 h-full rounded-full transition-all duration-700"
                              style={{ width: `${pctInversion}%` }}
                            />
                          </div>
                          <span className="w-16 font-bold text-amber-400">${lote.inversion}</span>
                        </div>

                        {/* Retorno */}
                        <div className="flex items-center text-[10px] space-x-2">
                          <span className="w-16 text-slate-400 font-semibold text-right">Retorno:</span>
                          <div className="flex-1 bg-slate-900 rounded-full h-3 overflow-hidden p-0.5">
                            <div
                              className="bg-gradient-to-r from-emerald-500 to-teal-400 h-full rounded-full transition-all duration-700"
                              style={{ width: `${pctRetorno}%` }}
                            />
                          </div>
                          <span className="w-16 font-bold text-emerald-400">${lote.retorno}</span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Leyenda del Gráfico */}
            <div className="mt-6 pt-4 border-t border-slate-800 flex items-center justify-around text-xs">
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 rounded-full bg-amber-400" />
                <span className="text-slate-300 font-medium">Inversión ($USD/ha)</span>
              </div>
              <div className="flex items-center space-x-2">
                <span className="w-3 h-3 rounded-full bg-emerald-400" />
                <span className="text-slate-300 font-medium">Retorno ($USD/ha)</span>
              </div>
            </div>
          </section>

        </div>

      </div>

      {/* =================================================================== */}
      {/* MODAL VER COMPROBANTE DIGITAL                                      */}
      {/* =================================================================== */}
      {modalComprobante && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-3xl max-w-lg w-full p-6 space-y-4 shadow-2xl animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-black text-white">{modalComprobante.concepto}</h3>
                <p className="text-xs text-slate-400">Comprobante Digital de Pago</p>
              </div>
              <button
                onClick={() => setModalComprobante(null)}
                className="p-2 text-slate-400 hover:text-slate-100 bg-slate-800 rounded-full"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Monto ARS:</span>
                <span className="font-bold text-white">${modalComprobante.montoArs.toLocaleString('es-AR')}</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Monto USD:</span>
                <span className="font-bold text-emerald-400">${modalComprobante.montoUsd.toFixed(2)} USD</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-800">
                <span className="text-slate-400">Estado:</span>
                <span className="font-bold uppercase text-amber-400">{modalComprobante.estado}</span>
              </div>
            </div>

            <div className="rounded-2xl overflow-hidden border border-slate-700 h-56 bg-slate-950 flex items-center justify-center relative">
              <img
                src={modalComprobante.comprobanteUrl}
                alt="Comprobante"
                className="object-cover w-full h-full opacity-80"
              />
              <div className="absolute bottom-3 left-3 bg-slate-950/80 backdrop-blur px-3 py-1 rounded-lg text-[11px] text-slate-300">
                📄 Documento Digital Verificado
              </div>
            </div>

            <button
              onClick={() => setModalComprobante(null)}
              className="w-full py-3 bg-slate-800 hover:bg-slate-700 text-slate-200 font-bold text-sm rounded-xl border border-slate-700"
            >
              Cerrar Vista Previa
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
