import React, { useState, useEffect } from 'react';
import { 
  CloudRain, 
  Tractor, 
  Mic, 
  MicOff, 
  CheckCircle2, 
  Circle, 
  AlertTriangle, 
  Wind, 
  Thermometer, 
  Droplets, 
  Wifi, 
  WifiOff, 
  Plus, 
  X, 
  MapPin, 
  Clock, 
  Save, 
  Volume2,
  Check,
  Calendar,
  Layers,
  FileText
} from 'lucide-react';

export default function ModoCampo() {
  // ---------------------------------------------------------------------------
  // Estado Global & Simulación de Sensores/Red
  // ---------------------------------------------------------------------------
  const [isOnline, setIsOnline] = useState(false); // Inicial en modo offline ("sobre la camioneta")
  const [pendingSyncCount, setPendingSyncCount] = useState(3);
  
  // Clima
  const [temperatura, setTemperatura] = useState(28);
  const [humedad, setHumedad] = useState(42);
  const [viento, setViento] = useState(18); // > 15 km/h dispara alerta de pulverización

  // Modales
  const [modalLluviaOpen, setModalLluviaOpen] = useState(false);
  const [modalLaborOpen, setModalLaborOpen] = useState(false);
  const [modalNotaOpen, setModalNotaOpen] = useState(false);

  // Notificaciones Toast
  const [toastMessage, setToastMessage] = useState(null);

  // ---------------------------------------------------------------------------
  // Datos de Prueba (Lotes y Tareas)
  // ---------------------------------------------------------------------------
  const lotes = [
    { id: 'lote-1', nombre: 'Lote 1 - El Norte', hectareas: 145, tipoSuelo: 'Argiudol Típico' },
    { id: 'lote-2', nombre: 'Lote 2 - La Lagunita', hectareas: 220, tipoSuelo: 'Haplustol' },
    { id: 'lote-3', nombre: 'Lote 3 - San José', hectareas: 90, tipoSuelo: 'Argiudol Típico' },
    { id: 'lote-4', nombre: 'Lote 4 - El Molino', hectareas: 310, tipoSuelo: 'Entisol' },
  ];

  const [tareas, setTareas] = useState([
    {
      id: 1,
      lote: 'Lote 2 - La Lagunita',
      tipo: 'Pulverización',
      descripcion: 'Aplicación de herbicida presiembra (Glifosato 2.5 l/ha + 2,4-D)',
      horario: '08:00 hs',
      completada: false,
      prioridad: 'alta',
    },
    {
      id: 2,
      lote: 'Lote 1 - El Norte',
      tipo: 'Monitoreo',
      descripcion: 'Control de oruga cogollera en cabecera oeste',
      horario: '11:30 hs',
      completada: true,
      prioridad: 'media',
    },
    {
      id: 3,
      lote: 'Lote 3 - San José',
      tipo: 'Mantenimiento',
      descripcion: 'Verificar nivel de aceite y grasa en tolva autodescargable',
      horario: '15:00 hs',
      completada: false,
      prioridad: 'normal',
    },
  ]);

  // Formulario Lluvia
  const [lluviaForm, setLluviaForm] = useState({
    loteId: 'lote-2',
    milimetros: '15.5',
    notas: '',
  });

  // Formulario Labor
  const [laborForm, setLaborForm] = useState({
    loteId: 'lote-1',
    tipoLabor: 'pulverizacion',
    campania: 'Trigo/Soja 2025-2026',
    producto: 'Glifosato 66.2%',
    dosis: '2.5',
    unidad: 'l/ha',
    estado: 'iniciar', // iniciar o finalizar
  });

  // Formulario Nota de Voz / Eventualidad
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [notaForm, setNotaForm] = useState({
    loteId: 'lote-2',
    categoria: 'Avería Maquinaria',
    texto: '',
    audioGrabado: false,
  });

  // Timer para simulación de grabación de voz
  useEffect(() => {
    let interval;
    if (isRecording) {
      interval = setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } else {
      setRecordingTime(0);
    }
    return () => clearInterval(interval);
  }, [isRecording]);

  const showToast = (msg) => {
    setToastMessage(msg);
    setTimeout(() => setToastMessage(null), 4000);
  };

  const toggleTarea = (id) => {
    setTareas(
      tareas.map((t) => (t.id === id ? { ...t, completada: !t.completada } : t))
    );
    const tarea = tareas.find((t) => t.id === id);
    if (tarea && !tarea.completada) {
      showToast(
        isOnline
          ? `✓ Tarea "${tarea.tipo}" completada y sincronizada`
          : `✓ Tarea completada (Guardada localmente)`
      );
      if (!isOnline) setPendingSyncCount((prev) => prev + 1);
    }
  };

  const handleGuardarLluvia = (e) => {
    e.preventDefault();
    const loteSel = lotes.find((l) => l.id === lluviaForm.loteId);
    showToast(
      isOnline
        ? `🌧️ Lluvia de ${lluviaForm.milimetros} mm registrada en ${loteSel?.nombre}`
        : `🌧️ Lluvia de ${lluviaForm.milimetros} mm guardada en celular (${loteSel?.nombre})`
    );
    if (!isOnline) setPendingSyncCount((prev) => prev + 1);
    setModalLluviaOpen(false);
  };

  const handleGuardarLabor = (e) => {
    e.preventDefault();
    const loteSel = lotes.find((l) => l.id === laborForm.loteId);
    const accion = laborForm.estado === 'iniciar' ? 'Iniciada' : 'Finalizada';
    showToast(
      isOnline
        ? `🚜 Labor de ${laborForm.tipoLabor.toUpperCase()} ${accion} en ${loteSel?.nombre}`
        : `🚜 Labor ${accion} guardada offline en ${loteSel?.nombre}`
    );
    if (!isOnline) setPendingSyncCount((prev) => prev + 1);
    setModalLaborOpen(false);
  };

  const handleGuardarNota = (e) => {
    e.preventDefault();
    showToast(
      isOnline
        ? `🎙️ Nota/Eventualidad registrada y enviada a administración`
        : `🎙️ Nota guardada en memoria local`
    );
    if (!isOnline) setPendingSyncCount((prev) => prev + 1);
    setIsRecording(false);
    setModalNotaOpen(false);
  };

  const alertaVientoAlto = viento > 15;

  return (
    <div className="min-h-screen bg-slate-900 text-slate-100 font-sans antialiased pb-12 select-none touch-manipulation">
      {/* =================================================================== */}
      {/* BARRA SUPERIOR DE ESTADO Y SINCRONIZACIÓN (OFFLINE-FIRST)          */}
      {/* =================================================================== */}
      <header className="sticky top-0 z-30 bg-slate-950/95 backdrop-blur border-b border-slate-800 px-4 py-3 shadow-md">
        <div className="max-w-md mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <div className="w-3 h-3 rounded-full bg-emerald-500 animate-pulse" />
            <span className="font-bold text-lg tracking-tight text-emerald-400">
              EduAgro <span className="text-xs font-normal px-2 py-0.5 bg-emerald-950 text-emerald-300 rounded-full border border-emerald-800">MODO CAMPO</span>
            </span>
          </div>

          {/* Badge de Sincronización Interactiva */}
          <button
            onClick={() => {
              setIsOnline(!isOnline);
              showToast(
                !isOnline
                  ? '🟢 Conexión restablecida. Sincronizando datos con PostgreSQL...'
                  : '🟡 Modo Offline activado. Se guardará en Almacenamiento Local.'
              );
            }}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-full text-xs font-semibold tracking-wide border transition-all active:scale-95 ${
              isOnline
                ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700 hover:bg-emerald-900'
                : 'bg-amber-950/80 text-amber-300 border-amber-600 animate-pulse hover:bg-amber-900'
            }`}
            title="Toca para simular cambio de señal/red"
          >
            {isOnline ? (
              <>
                <Wifi className="w-3.5 h-3.5 text-emerald-400" />
                <span>🟢 Sincronizado</span>
              </>
            ) : (
              <>
                <WifiOff className="w-3.5 h-3.5 text-amber-400" />
                <span>🟡 Guardado en dispositivo ({pendingSyncCount})</span>
              </>
            )}
          </button>
        </div>
      </header>

      {/* TOAST DE NOTIFICACIÓN DE ESTADO */}
      {toastMessage && (
        <div className="fixed top-16 left-4 right-4 z-50 max-w-md mx-auto bg-slate-800 text-slate-100 px-4 py-3 rounded-xl border border-slate-700 shadow-2xl flex items-center space-x-3 animate-bounce">
          <div className="bg-emerald-500/20 p-2 rounded-lg text-emerald-400">
            <Check className="w-5 h-5" />
          </div>
          <p className="text-sm font-medium text-slate-200">{toastMessage}</p>
        </div>
      )}

      <main className="max-w-md mx-auto px-4 pt-4 space-y-5">
        {/* =================================================================== */}
        {/* 1. HEADER CLIMA & ALERTA AGRONÓMICA                                 */}
        {/* =================================================================== */}
        <section className="bg-slate-800/90 rounded-2xl p-4 border border-slate-700 shadow-lg space-y-3">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span className="flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5 text-emerald-400" /> Zona de Producción
            </span>
            <span className="flex items-center gap-1">
              <Clock className="w-3.5 h-3.5 text-slate-400" /> Actualizado 10:45 hs
            </span>
          </div>

          {/* Métricas Climáticas en Cuadrícula */}
          <div className="grid grid-cols-3 gap-2 py-1">
            <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex flex-col items-center justify-center">
              <div className="flex items-center text-amber-400 mb-1">
                <Thermometer className="w-5 h-5 mr-1" />
                <span className="text-2xl font-black">{temperatura}°</span>
              </div>
              <span className="text-[11px] text-slate-400 font-semibold tracking-wider uppercase">Temp (°C)</span>
            </div>

            <div className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex flex-col items-center justify-center">
              <div className="flex items-center text-cyan-400 mb-1">
                <Droplets className="w-5 h-5 mr-1" />
                <span className="text-2xl font-black">{humedad}%</span>
              </div>
              <span className="text-[11px] text-slate-400 font-semibold tracking-wider uppercase">Humedad</span>
            </div>

            <button 
              onClick={() => {
                const nextViento = viento > 15 ? 12 : 22;
                setViento(nextViento);
              }}
              className="bg-slate-900/80 p-3 rounded-xl border border-slate-800 flex flex-col items-center justify-center active:scale-95 transition-transform"
              title="Toca para cambiar viento y testear alerta"
            >
              <div className={`flex items-center mb-1 ${alertaVientoAlto ? 'text-amber-400 font-bold' : 'text-blue-400'}`}>
                <Wind className="w-5 h-5 mr-1" />
                <span className="text-2xl font-black">{viento}</span>
                <span className="text-xs font-normal ml-0.5">km/h</span>
              </div>
              <span className="text-[11px] text-slate-400 font-semibold tracking-wider uppercase">Viento</span>
            </button>
          </div>

          {/* Badge Dinámico de Alerta Agronómica */}
          {alertaVientoAlto ? (
            <div className="bg-amber-500/15 border-2 border-amber-500/60 p-3 rounded-xl flex items-start space-x-3 text-amber-300">
              <AlertTriangle className="w-6 h-6 text-amber-400 shrink-0 mt-0.5 animate-pulse" />
              <div>
                <h4 className="font-bold text-sm tracking-wide text-amber-200">
                  Alerta Pulverización: Viento Alto ({viento} km/h)
                </h4>
                <p className="text-xs text-amber-300/90 mt-0.5">
                  Supera el límite recomendado (&gt;15 km/h). Riesgo elevado de deriva de producto.
                </p>
              </div>
            </div>
          ) : (
            <div className="bg-emerald-500/10 border border-emerald-500/40 p-2.5 rounded-xl flex items-center space-x-2.5 text-emerald-300">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <span className="text-xs font-semibold">
                Condiciones Óptimas de Aplicación (Viento {viento} km/h)
              </span>
            </div>
          )}
        </section>

        {/* =================================================================== */}
        {/* 2. PANEL DE BOTONES GIGANTES DE ACCIÓN RÁPIDA (MIN 80PX ALTO)      */}
        {/* =================================================================== */}
        <section className="space-y-3">
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400 px-1">
            Acciones Rápidas Táctiles
          </h2>

          <div className="grid grid-cols-1 gap-3">
            {/* BOTÓN 1: REGISTRAR LLUVIA */}
            <button
              onClick={() => setModalLluviaOpen(true)}
              className="min-h-[84px] w-full bg-gradient-to-r from-blue-600 to-cyan-600 hover:from-blue-500 hover:to-cyan-500 active:scale-[0.98] text-white p-4 rounded-2xl shadow-lg border border-cyan-400/30 flex items-center justify-between transition-all"
            >
              <div className="flex items-center space-x-4">
                <div className="bg-white/20 p-3 rounded-xl backdrop-blur">
                  <CloudRain className="w-8 h-8 text-white" />
                </div>
                <div className="text-left">
                  <span className="block text-xl font-black tracking-tight">Registrar Lluvia</span>
                  <span className="text-xs text-cyan-100/90 font-medium">Carga de milímetros por lote</span>
                </div>
              </div>
              <span className="bg-white/20 text-white font-bold text-sm px-3 py-1.5 rounded-xl backdrop-blur">
                + mm
              </span>
            </button>

            {/* BOTÓN 2: INICIAR / FIN LABOR */}
            <button
              onClick={() => setModalLaborOpen(true)}
              className="min-h-[84px] w-full bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 active:scale-[0.98] text-white p-4 rounded-2xl shadow-lg border border-teal-400/30 flex items-center justify-between transition-all"
            >
              <div className="flex items-center space-x-4">
                <div className="bg-white/20 p-3 rounded-xl backdrop-blur">
                  <Tractor className="w-8 h-8 text-white" />
                </div>
                <div className="text-left">
                  <span className="block text-xl font-black tracking-tight">Iniciar / Fin Labor</span>
                  <span className="text-xs text-emerald-100/90 font-medium">Siembra, Pulverización, Cosecha</span>
                </div>
              </div>
              <span className="bg-white/20 text-white font-bold text-sm px-3 py-1.5 rounded-xl backdrop-blur">
                🚜 Cargar
              </span>
            </button>

            {/* BOTÓN 3: NOTA DE VOZ / EVENTUALIDAD */}
            <button
              onClick={() => setModalNotaOpen(true)}
              className="min-h-[84px] w-full bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 active:scale-[0.98] text-white p-4 rounded-2xl shadow-lg border border-orange-400/30 flex items-center justify-between transition-all"
            >
              <div className="flex items-center space-x-4">
                <div className="bg-white/20 p-3 rounded-xl backdrop-blur">
                  <Mic className="w-8 h-8 text-white" />
                </div>
                <div className="text-left">
                  <span className="block text-xl font-black tracking-tight">Nota de Voz / Novedad</span>
                  <span className="text-xs text-amber-100/90 font-medium">Dictado por audio o averías</span>
                </div>
              </div>
              <span className="bg-white/20 text-white font-bold text-sm px-3 py-1.5 rounded-xl backdrop-blur">
                🎙️ Audio
              </span>
            </button>
          </div>
        </section>

        {/* =================================================================== */}
        {/* 3. LISTADO DE TAREAS ASIGNADAS (CHECKBOXES GIGANTES)                */}
        {/* =================================================================== */}
        <section className="space-y-3 pt-2">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-xs font-bold uppercase tracking-wider text-slate-400">
              Tareas Asignadas del Día ({tareas.filter(t => t.completada).length}/{tareas.length})
            </h2>
            <span className="text-xs text-emerald-400 font-semibold">Hoy, 27 Jul</span>
          </div>

          <div className="space-y-2.5">
            {tareas.map((tarea) => (
              <div
                key={tarea.id}
                onClick={() => toggleTarea(tarea.id)}
                className={`p-4 rounded-2xl border transition-all cursor-pointer flex items-start space-x-4 active:scale-[0.99] ${
                  tarea.completada
                    ? 'bg-slate-900/60 border-slate-800 text-slate-500 opacity-75'
                    : 'bg-slate-800 border-slate-700 text-slate-100 shadow-md hover:border-slate-600'
                }`}
              >
                {/* Checkbox Táctil Gigante */}
                <div className="pt-0.5">
                  {tarea.completada ? (
                    <div className="w-8 h-8 rounded-xl bg-emerald-500 text-slate-950 flex items-center justify-center shadow-inner">
                      <Check className="w-6 h-6 stroke-[3]" />
                    </div>
                  ) : (
                    <div className="w-8 h-8 rounded-xl border-2 border-slate-500 hover:border-emerald-400 flex items-center justify-center bg-slate-900/50">
                      <Circle className="w-5 h-5 text-transparent" />
                    </div>
                  )}
                </div>

                {/* Contenido de la Tarjeta */}
                <div className="flex-1 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-slate-700 text-slate-300">
                      {tarea.lote}
                    </span>
                    <span className="text-xs text-slate-400 font-medium">{tarea.horario}</span>
                  </div>
                  <h3 className={`font-bold text-base ${tarea.completada ? 'line-through text-slate-400' : 'text-slate-100'}`}>
                    {tarea.tipo}
                  </h3>
                  <p className={`text-xs leading-relaxed ${tarea.completada ? 'text-slate-500' : 'text-slate-300'}`}>
                    {tarea.descripcion}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </section>
      </main>

      {/* =================================================================== */}
      {/* MODAL 1: REGISTRAR LLUVIA                                          */}
      {/* =================================================================== */}
      {modalLluviaOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-t-3xl sm:rounded-3xl p-6 space-y-5 animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-3 text-cyan-400">
                <CloudRain className="w-7 h-7" />
                <h3 className="text-xl font-black text-slate-100">Registrar Lluvia</h3>
              </div>
              <button
                onClick={() => setModalLluviaOpen(false)}
                className="p-2 text-slate-400 hover:text-slate-100 rounded-full bg-slate-800"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleGuardarLluvia} className="space-y-4">
              {/* Selección de Lote */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Seleccionar Lote
                </label>
                <select
                  value={lluviaForm.loteId}
                  onChange={(e) => setLluviaForm({ ...lluviaForm, loteId: e.target.value })}
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3.5 text-base font-bold text-slate-100 focus:ring-2 focus:ring-cyan-500 focus:outline-none"
                >
                  {lotes.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nombre} ({l.hectareas} ha)
                    </option>
                  ))}
                </select>
              </div>

              {/* Input Milímetros con keypad grande */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Precipitación (Milímetros mm)
                </label>
                <div className="relative">
                  <input
                    type="number"
                    step="0.5"
                    value={lluviaForm.milimetros}
                    onChange={(e) => setLluviaForm({ ...lluviaForm, milimetros: e.target.value })}
                    placeholder="0.0"
                    required
                    className="w-full bg-slate-800 border-2 border-cyan-500/50 rounded-2xl p-4 text-3xl font-black text-cyan-300 text-center focus:ring-4 focus:ring-cyan-500/20 focus:outline-none"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 text-slate-400 font-bold text-lg">
                    mm
                  </span>
                </div>
              </div>

              {/* Accesos rápidos de números */}
              <div className="grid grid-cols-4 gap-2 pt-1">
                {['5', '10', '15.5', '25', '35', '50', '75', '100'].map((mm) => (
                  <button
                    key={mm}
                    type="button"
                    onClick={() => setLluviaForm({ ...lluviaForm, milimetros: mm })}
                    className="bg-slate-800 hover:bg-slate-700 active:bg-cyan-600 text-slate-200 py-2 rounded-xl text-sm font-bold border border-slate-700"
                  >
                    {mm} mm
                  </button>
                ))}
              </div>

              {/* Botón Guardar */}
              <button
                type="submit"
                className="w-full min-h-[56px] bg-cyan-600 hover:bg-cyan-500 active:scale-95 text-white text-lg font-black rounded-2xl shadow-lg flex items-center justify-center space-x-2 mt-4"
              >
                <Save className="w-6 h-6" />
                <span>{isOnline ? 'Guardar y Sincronizar' : 'Guardar en Celular (Offline)'}</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 2: INICIAR / FIN LABOR                                       */}
      {/* =================================================================== */}
      {modalLaborOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-t-3xl sm:rounded-3xl p-6 space-y-5 animate-in slide-in-from-bottom duration-200 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-3 text-emerald-400">
                <Tractor className="w-7 h-7" />
                <h3 className="text-xl font-black text-slate-100">Registro de Labor</h3>
              </div>
              <button
                onClick={() => setModalLaborOpen(false)}
                className="p-2 text-slate-400 hover:text-slate-100 rounded-full bg-slate-800"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleGuardarLabor} className="space-y-4">
              {/* Tipo de Labor */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Tipo de Labor
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: 'pulverizacion', label: 'Pulverización', emoji: '🧪' },
                    { id: 'siembra', label: 'Siembra', emoji: '🌱' },
                    { id: 'cosecha', label: 'Cosecha', emoji: '🌾' },
                    { id: 'fertilizacion', label: 'Fertilización', emoji: '⚡' },
                  ].map((tipo) => (
                    <button
                      key={tipo.id}
                      type="button"
                      onClick={() => setLaborForm({ ...laborForm, tipoLabor: tipo.id })}
                      className={`p-3 rounded-xl border text-sm font-bold flex items-center justify-start space-x-2 ${
                        laborForm.tipoLabor === tipo.id
                          ? 'bg-emerald-600 text-white border-emerald-400'
                          : 'bg-slate-800 text-slate-300 border-slate-700'
                      }`}
                    >
                      <span className="text-lg">{tipo.emoji}</span>
                      <span>{tipo.label}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Lote */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Lote de Trabajo
                </label>
                <select
                  value={laborForm.loteId}
                  onChange={(e) => setLaborForm({ ...laborForm, loteId: e.target.value })}
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3.5 text-base font-bold text-slate-100 focus:outline-none"
                >
                  {lotes.map((l) => (
                    <option key={l.id} value={l.id}>
                      {l.nombre} ({l.hectareas} ha)
                    </option>
                  ))}
                </select>
              </div>

              {/* Insumos / Producto */}
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                    Producto / Insumo
                  </label>
                  <input
                    type="text"
                    value={laborForm.producto}
                    onChange={(e) => setLaborForm({ ...laborForm, producto: e.target.value })}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-sm text-slate-100 font-medium"
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                    Dosis / Dosis ha
                  </label>
                  <input
                    type="text"
                    value={laborForm.dosis}
                    onChange={(e) => setLaborForm({ ...laborForm, dosis: e.target.value })}
                    className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-sm text-slate-100 font-bold"
                  />
                </div>
              </div>

              {/* Estado de la Labor */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Estado de Avance
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setLaborForm({ ...laborForm, estado: 'iniciar' })}
                    className={`py-3 rounded-xl text-sm font-bold border ${
                      laborForm.estado === 'iniciar'
                        ? 'bg-blue-600 border-blue-400 text-white'
                        : 'bg-slate-800 border-slate-700 text-slate-400'
                    }`}
                  >
                    ▶️ Iniciar Labor
                  </button>
                  <button
                    type="button"
                    onClick={() => setLaborForm({ ...laborForm, estado: 'finalizar' })}
                    className={`py-3 rounded-xl text-sm font-bold border ${
                      laborForm.estado === 'finalizar'
                        ? 'bg-emerald-600 border-emerald-400 text-white'
                        : 'bg-slate-800 border-slate-700 text-slate-400'
                    }`}
                  >
                    ⏹️ Finalizar Labor
                  </button>
                </div>
              </div>

              <button
                type="submit"
                className="w-full min-h-[56px] bg-emerald-600 hover:bg-emerald-500 active:scale-95 text-white text-lg font-black rounded-2xl shadow-lg flex items-center justify-center space-x-2 mt-4"
              >
                <Save className="w-6 h-6" />
                <span>Confirmar Registro de Labor</span>
              </button>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 3: NOTA DE VOZ / EVENTUALIDAD                                */}
      {/* =================================================================== */}
      {modalNotaOpen && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4">
          <div className="w-full max-w-md bg-slate-900 border border-slate-700 rounded-t-3xl sm:rounded-3xl p-6 space-y-5 animate-in slide-in-from-bottom duration-200">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center space-x-3 text-amber-400">
                <Mic className="w-7 h-7" />
                <h3 className="text-xl font-black text-slate-100">Nota / Eventualidad</h3>
              </div>
              <button
                onClick={() => setModalNotaOpen(false)}
                className="p-2 text-slate-400 hover:text-slate-100 rounded-full bg-slate-800"
              >
                <X className="w-6 h-6" />
              </button>
            </div>

            <form onSubmit={handleGuardarNota} className="space-y-4">
              {/* Botón Gigante Dictar por Voz */}
              <div className="text-center py-2 space-y-3 bg-slate-950/60 p-4 rounded-2xl border border-slate-800">
                <button
                  type="button"
                  onClick={() => setIsRecording(!isRecording)}
                  className={`w-20 h-20 rounded-full mx-auto flex items-center justify-center transition-all shadow-xl active:scale-90 ${
                    isRecording
                      ? 'bg-red-600 text-white animate-pulse ring-8 ring-red-950'
                      : 'bg-amber-500 hover:bg-amber-400 text-slate-950'
                  }`}
                >
                  {isRecording ? <MicOff className="w-10 h-10" /> : <Mic className="w-10 h-10" />}
                </button>
                <div>
                  <span className="block text-sm font-bold text-slate-200">
                    {isRecording ? `🔴 Grabando Audio (00:0${recordingTime})` : 'Toca para Dictar Nota de Voz'}
                  </span>
                  <span className="text-xs text-slate-400">
                    {isRecording ? 'Presiona nuevamente para detener' : 'Captura directa "sobre la camioneta"'}
                  </span>
                </div>
              </div>

              {/* Categoria rápida */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Tipo de Novedad
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {['Avería Maquinaria', 'Maleza/Plaga', 'Camino/Alambrado', 'Otro'].map((cat) => (
                    <button
                      key={cat}
                      type="button"
                      onClick={() => setNotaForm({ ...notaForm, categoria: cat })}
                      className={`p-2.5 rounded-xl border text-xs font-bold ${
                        notaForm.categoria === cat
                          ? 'bg-amber-600 text-white border-amber-400'
                          : 'bg-slate-800 text-slate-300 border-slate-700'
                      }`}
                    >
                      {cat}
                    </button>
                  ))}
                </div>
              </div>

              {/* Texto Alternativo / Notas escritas */}
              <div>
                <label className="block text-xs font-bold uppercase text-slate-400 mb-1.5">
                  Descripción (o Texto Dictado)
                </label>
                <textarea
                  rows="3"
                  value={notaForm.texto}
                  onChange={(e) => setNotaForm({ ...notaForm, texto: e.target.value })}
                  placeholder="Ej: Rotura de manguera en pulverizadora / Mancha de sorgo de alepo en cabecera norte..."
                  className="w-full bg-slate-800 border border-slate-700 rounded-xl p-3 text-sm text-slate-100 focus:outline-none"
                />
              </div>

              <button
                type="submit"
                className="w-full min-h-[56px] bg-amber-600 hover:bg-amber-500 active:scale-95 text-white text-lg font-black rounded-2xl shadow-lg flex items-center justify-center space-x-2 mt-4"
              >
                <Save className="w-6 h-6" />
                <span>Guardar Novedad</span>
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
