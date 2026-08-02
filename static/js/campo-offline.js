// ==========================================
// EduAgro Modo Campo Offline-First Engine
// Synchronous Form Interception + Real-Time IndexedDB State & Debug Logging
// ==========================================

const DB_NAME = 'EduAgroOfflineDB';
const DB_VERSION = 1;

let dbPromise = null;
let currentFilterState = 'todas';
let isActuallyOffline = !navigator.onLine;

// Helper de Logging de Depuración Visible en Consola
function logDebug(emoji, step, details = '') {
  console.log(`%c[OFFLINE ENGINE ${emoji}] %c${step}%c ${details ? JSON.stringify(details) : ''}`,
    'color: #059669; font-weight: bold;',
    'color: #0284c7; font-weight: bold;',
    'color: #475569;'
  );
}

// 1. Inicialización de IndexedDB
function openOfflineDB() {
  if (dbPromise) return dbPromise;

  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;

      if (!db.objectStoreNames.contains('campo_activo_cache')) {
        db.createObjectStore('campo_activo_cache', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('tareas_cache')) {
        db.createObjectStore('tareas_cache', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('clima_cache')) {
        db.createObjectStore('clima_cache', { keyPath: 'id' });
      }
      if (!db.objectStoreNames.contains('offline_queue')) {
        db.createObjectStore('offline_queue', { keyPath: 'client_action_id' });
      }
    };

    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

  return dbPromise;
}

// Helpers para operaciones en IndexedDB
async function idbWrite(storeName, data) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    if (Array.isArray(data)) {
      data.forEach((item) => store.put(item));
    } else {
      store.put(data);
    }
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

async function idbGetAll(storeName) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readonly');
    const store = tx.objectStore(storeName);
    const req = store.getAll();
    req.onsuccess = () => resolve(req.result || []);
    req.onerror = () => reject(req.error);
  });
}

async function idbDelete(storeName, key) {
  const db = await openOfflineDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, 'readwrite');
    const store = tx.objectStore(storeName);
    store.delete(key);
    tx.oncomplete = () => resolve(true);
    tx.onerror = () => reject(tx.error);
  });
}

// 2. Poblar tareas_cache desde HTML Jinja en la primera carga si IndexedDB está vacío
async function seedIDBFromSSRHtml() {
  const existing = await idbGetAll('tareas_cache');
  if (existing && existing.length > 0) return;

  const cardElements = document.querySelectorAll('#tasks-feed-container .task-card');
  if (!cardElements || cardElements.length === 0) return;

  const scrapedTasks = [];
  cardElements.forEach((card, index) => {
    const typeBadge = card.querySelector('.task-type-badge');
    const loteBadge = card.querySelector('.task-lote-badge');
    const titleElem = card.querySelector('.task-card-body h3');
    const obsElem = card.querySelector('.task-card-body p');
    const metaRow = card.querySelector('.meta-row');
    const metaValElem = card.querySelector('.meta-val');

    let id = `tarea-00${index + 1}`;
    const form = card.querySelector('form');
    if (form) {
      const act = form.getAttribute('action') || form.action || '';
      const match = act.match(/\/campo\/tareas\/([^\/]+)/);
      if (match && match[1]) id = match[1];
    }

    let estado = 'pendiente';
    if (card.classList.contains('status-en-curso')) estado = 'en_curso';
    else if (card.classList.contains('status-hecha')) estado = 'hecha';

    let responsable = 'Operario Campo';
    if (metaRow) {
      const respText = metaRow.textContent || '';
      if (respText.includes('👤')) {
        responsable = respText.split('👤')[1].split('\n')[0].trim();
      }
    }

    scrapedTasks.push({
      id: id,
      campo_id: 'campo-001',
      campo_nombre: 'Campo Activo',
      lote_id: null,
      lote_nombre: loteBadge ? loteBadge.textContent.replace('📍', '').trim() : null,
      tipo: 'siembra',
      tipo_label: typeBadge ? typeBadge.textContent.trim() : '🌾 Labor',
      titulo: titleElem ? titleElem.textContent.trim() : 'Tarea de Campo',
      responsable: responsable,
      prioridad: 'media',
      prioridad_label: 'Media',
      estado: estado,
      estado_label: estado === 'en_curso' ? 'En Curso' : (estado === 'hecha' ? 'Hecha' : 'Pendiente'),
      fecha: new Date().toISOString().split('T')[0],
      observaciones: obsElem ? obsElem.textContent.trim() : '',
      valor_registrado: metaValElem ? metaValElem.textContent.trim() : null
    });
  });

  if (scrapedTasks.length > 0) {
    await idbWrite('tareas_cache', scrapedTasks);
    logDebug('🌱', 'IDB Hidratado desde HTML SSR', { cantidad: scrapedTasks.length });
  }
}

// 3. Guardar estado fresco obtenido del backend en IndexedDB
async function cacheStateInIDB(state) {
  if (!state) return;
  try {
    if (state.campo_activo) {
      await idbWrite('campo_activo_cache', state.campo_activo);
    }
    if (state.weather) {
      await idbWrite('clima_cache', { id: 'current', ...state.weather });
    }
    if (state.tareas && Array.isArray(state.tareas)) {
      const db = await openOfflineDB();
      const tx = db.transaction('tareas_cache', 'readwrite');
      const store = tx.objectStore('tareas_cache');
      store.clear();
      state.tareas.forEach((t) => store.put(t));
    }
  } catch (err) {
    console.warn('[Offline DB] Error actualizando caché local:', err);
  }
}

// 4. Generar ID único para idempotencia de acciones en cola
function generateClientActionId() {
  return 'act-' + Date.now() + '-' + Math.random().toString(36).substring(2, 9);
}

// 5. Encolar Acción Offline en IndexedDB y actualizar vista local inmediatamente
async function processFieldAction(tipo, payload) {
  logDebug('⚡', 'Procesando Acción de Campo', { tipo, payload });

  const clientAction = {
    client_action_id: generateClientActionId(),
    tipo: tipo,
    payload: payload,
    timestamp: new Date().toISOString(),
    status: 'pending'
  };

  // Guardar en cola offline_queue
  await idbWrite('offline_queue', clientAction);
  logDebug('💾', 'Acción guardada en offline_queue', { id: clientAction.client_action_id });

  // Optimismo Local: Actualizar tareas_cache en IndexedDB
  await applyOptimisticTaskUpdate(tipo, payload);
  logDebug('🔄', 'IndexedDB tareas_cache actualizada');

  // Renderizar UI inmediatamente
  await renderTasksFromIDB(currentFilterState);
  logDebug('🎨', 'Renderizado de UI disparado');

  // Actualizar Badges y Banner
  await updateUIBadges();
  logDebug('🔔', 'Banner y badges actualizados');

  // Si estamos en línea, intentar enviar en segundo plano de inmediato
  if (navigator.onLine && !isActuallyOffline) {
    syncOfflineQueue().catch(() => {
      logDebug('📡', 'Sync en background pospuesto (red no disponible real)');
      isActuallyOffline = true;
      updateUIBadges();
    });
  }
}

// 6. Actualización Optimista de Tareas Locales en IndexedDB
async function applyOptimisticTaskUpdate(tipo, payload) {
  const nowStr = new Date().toISOString().split('T')[0];

  if (tipo === 'registrar_lluvia') {
    const mm = payload.milimetros || 0;
    const newTask = {
      id: 'local-' + Date.now(),
      campo_id: payload.campo_id || 'campo-001',
      campo_nombre: 'Campo Activo',
      lote_id: payload.lote_id || null,
      lote_nombre: payload.lote_id ? 'Lote Seleccionado' : 'Campo General',
      tipo: 'lluvia_suelo',
      tipo_label: '🌧️ Lluvia / Suelo',
      titulo: `Registro de Lluvia (${mm} mm)`,
      responsable: 'Operario Campo',
      prioridad: 'media',
      prioridad_label: 'Media',
      estado: 'hecha',
      estado_label: 'Hecha',
      fecha: nowStr,
      observaciones: payload.observaciones || `Lluvia de ${mm} mm registrada offline.`,
      valor_registrado: `${mm} mm`
    };
    await idbWrite('tareas_cache', newTask);
  } else if (tipo === 'registrar_incidencia') {
    const newTask = {
      id: 'local-' + Date.now(),
      campo_id: payload.campo_id || 'campo-001',
      campo_nombre: 'Campo Activo',
      lote_id: payload.lote_id || null,
      lote_nombre: payload.lote_id ? 'Lote Seleccionado' : 'Campo General',
      tipo: 'incidencia',
      tipo_label: '⚠️ Novedad / Incidencia',
      titulo: payload.titulo || 'Incidencia de Campo',
      responsable: 'Operario Campo',
      prioridad: payload.prioridad || 'alta',
      prioridad_label: (payload.prioridad || 'alta').toUpperCase(),
      estado: 'pendiente',
      estado_label: 'Pendiente',
      fecha: nowStr,
      observaciones: payload.observaciones || 'Incidencia reportada offline.',
      valor_registrado: 'Reporte de Campo'
    };
    await idbWrite('tareas_cache', newTask);
  } else if (tipo === 'movimiento_stock') {
    const insumo = payload.insumo || 'Insumo';
    const cant = payload.cantidad || 0;
    const unidad = payload.unidad || 'litros';
    const newTask = {
      id: 'local-' + Date.now(),
      campo_id: payload.campo_id || 'campo-001',
      campo_nombre: 'Campo Activo',
      lote_id: null,
      lote_nombre: 'Galpón / Depósito',
      tipo: 'stock_insumos',
      tipo_label: '📦 Stock e Insumos',
      titulo: `Consumo/Retiro: ${insumo}`,
      responsable: 'Operario Campo',
      prioridad: 'media',
      prioridad_label: 'Media',
      estado: 'hecha',
      estado_label: 'Hecha',
      fecha: nowStr,
      observaciones: payload.observaciones || `Retiro de ${cant} ${unidad} registrado offline.`,
      valor_registrado: `${cant} ${unidad}`
    };
    await idbWrite('tareas_cache', newTask);
  } else if (tipo === 'nueva_labor') {
    const newTask = {
      id: 'local-' + Date.now(),
      campo_id: payload.campo_id || 'campo-001',
      campo_nombre: 'Campo Activo',
      lote_id: payload.lote_id || null,
      lote_nombre: payload.lote_id ? 'Lote Asignado' : 'Campo General',
      tipo: payload.tipo || 'siembra',
      tipo_label: '🌾 Labor Campo',
      titulo: payload.titulo || 'Nueva Labor',
      responsable: payload.responsable || 'Operario Campo',
      prioridad: payload.prioridad || 'media',
      prioridad_label: (payload.prioridad || 'media').toUpperCase(),
      estado: 'pendiente',
      estado_label: 'Pendiente',
      fecha: nowStr,
      observaciones: payload.observaciones || 'Labor programada offline.',
      valor_registrado: 'Programada'
    };
    await idbWrite('tareas_cache', newTask);
  } else if (tipo === 'iniciar_labor' && payload.tarea_id) {
    const tareas = await idbGetAll('tareas_cache');
    const target = tareas.find((t) => t.id === payload.tarea_id);
    if (target) {
      target.estado = 'en_curso';
      target.estado_label = 'En Curso';
      await idbWrite('tareas_cache', target);
    }
  } else if (tipo === 'completar_tarea' && payload.tarea_id) {
    const tareas = await idbGetAll('tareas_cache');
    const target = tareas.find((t) => t.id === payload.tarea_id);
    if (target) {
      target.estado = 'hecha';
      target.estado_label = 'Hecha';
      await idbWrite('tareas_cache', target);
    }
  }
}

// 7. Renderizado Dinámico del Feed de Tareas desde IndexedDB
async function renderTasksFromIDB(filterState = 'todas') {
  currentFilterState = filterState;
  const container = document.getElementById('tasks-feed-container');
  if (!container) return;

  let tareas = await idbGetAll('tareas_cache');

  if (!tareas || tareas.length === 0) {
    await seedIDBFromSSRHtml();
    tareas = await idbGetAll('tareas_cache');
  }

  tareas.reverse();

  const pendientesCount = tareas.filter((t) => t.estado === 'pendiente').length;
  const enCursoCount = tareas.filter((t) => t.estado === 'en_curso').length;
  const hechasCount = tareas.filter((t) => t.estado === 'hecha').length;
  const totalCount = tareas.length;

  const countHeader = document.getElementById('tasks-count-header');
  if (countHeader) countHeader.textContent = `Tareas del Campo Hoy (${totalCount})`;

  const badgePendiente = document.getElementById('count-pendiente');
  if (badgePendiente) badgePendiente.textContent = pendientesCount;
  const badgeEnCurso = document.getElementById('count-en-curso');
  if (badgeEnCurso) badgeEnCurso.textContent = enCursoCount;
  const badgeHecha = document.getElementById('count-hecha');
  if (badgeHecha) badgeHecha.textContent = hechasCount;
  const badgeTodas = document.getElementById('count-todas');
  if (badgeTodas) badgeTodas.textContent = totalCount;

  let filtered = tareas;
  if (filterState === 'pendiente') filtered = tareas.filter((t) => t.estado === 'pendiente');
  else if (filterState === 'en_curso') filtered = tareas.filter((t) => t.estado === 'en_curso');
  else if (filterState === 'hecha') filtered = tareas.filter((t) => t.estado === 'hecha');

  if (filtered.length === 0) {
    container.innerHTML = `
      <div style="background-color: #ffffff; padding: 2rem; border-radius: 20px; border: 1.5px solid #e2e8f0; text-align: center; display: flex; flex-direction: column; gap: 0.5rem;">
        <div style="font-size: 2.5rem;">🌱</div>
        <h3 style="font-size: 1rem; font-weight: 900; color: #0f172a;">No hay tareas en este estado</h3>
        <p style="font-size: 0.75rem; color: #64748b;">Seleccioná otro filtro o registrá una nueva labor usando los botones de arriba.</p>
      </div>
    `;
    return;
  }

  let html = '<div style="display: flex; flex-direction: column; gap: 0.75rem;">';

  filtered.forEach((t) => {
    let statusClass = '';
    let badgeHtml = '';

    if (t.estado === 'en_curso') {
      statusClass = 'status-en-curso';
      badgeHtml = '<span class="badge badge-amber">● En Curso</span>';
    } else if (t.estado === 'hecha') {
      statusClass = 'status-hecha';
      badgeHtml = '<span class="badge badge-agro">✓ Hecha</span>';
    } else {
      badgeHtml = '<span class="badge badge-slate">⏳ Pendiente</span>';
    }

    let ctaHtml = '';
    if (t.estado === 'pendiente') {
      ctaHtml = `
        <form method="POST" action="/campo/tareas/${t.id}/iniciar" style="flex: 2;">
          <button type="submit" class="btn-touch btn-amber" style="min-height: 48px; font-size: 0.85rem;">
            ▶️ Iniciar Labor
          </button>
        </form>
        <form method="POST" action="/campo/tareas/${t.id}/completar" style="flex: 1;">
          <button type="submit" class="btn-touch btn-outline-slate" style="min-height: 48px; font-size: 0.8rem; font-weight: 800;">
            ✓ Hecha
          </button>
        </form>
      `;
    } else if (t.estado === 'en_curso') {
      ctaHtml = `
        <form method="POST" action="/campo/tareas/${t.id}/completar" style="width: 100%;">
          <button type="submit" class="btn-touch btn-agro" style="min-height: 50px; font-size: 0.95rem;">
            ✓ Marcar Labor Realizada
          </button>
        </form>
      `;
    } else {
      ctaHtml = `
        <div style="width: 100%; padding: 0.6rem; background-color: #f0fdf4; color: #166534; border: 1px solid #bbf7d0; font-size: 0.8rem; font-weight: 800; border-radius: 12px; text-align: center;">
          ✓ Labor Concluida y Registrada
        </div>
      `;
    }

    const obsShort = t.observaciones ? (t.observaciones.length > 80 ? t.observaciones.substring(0, 80) + '...' : t.observaciones) : '';

    html += `
      <div class="task-card ${statusClass}">
        <div class="task-card-header">
          <div style="display: flex; align-items: center; gap: 0.4rem;">
            <span class="task-type-badge">${t.tipo_label || '🌾 Labor'}</span>
            ${t.lote_nombre ? `<span class="task-lote-badge">📍 ${t.lote_nombre}</span>` : ''}
          </div>
          ${badgeHtml}
        </div>
        <div class="task-card-body">
          <h3>${t.titulo}</h3>
          ${obsShort ? `<p>${obsShort}</p>` : ''}
        </div>
        <div class="task-card-footer">
          <div class="meta-row">
            <span>👤 ${t.responsable || 'Operario'}</span>
            ${t.valor_registrado ? `<span class="meta-val">${t.valor_registrado}</span>` : ''}
          </div>
          <div class="cta-row">${ctaHtml}</div>
        </div>
      </div>
    `;
  });

  html += '</div>';
  container.innerHTML = html;
}

// 8. Sincronizar Cola Offline con Backend (/api/campo/sync-actions)
let isSyncing = false;

async function syncOfflineQueue() {
  if (!navigator.onLine || isSyncing) {
    return;
  }

  const queue = await idbGetAll('offline_queue');
  if (!queue || queue.length === 0) {
    await updateUIBadges();
    return;
  }

  isSyncing = true;
  logDebug('🔄', 'Iniciando resincronización de cola...', { cantidad: queue.length });

  try {
    const response = await fetch('/api/campo/sync-actions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actions: queue })
    });

    if (response.ok) {
      const result = await response.json();
      logDebug('✓', 'Resincronización exitosa desde servidor:', result);

      for (const item of queue) {
        await idbDelete('offline_queue', item.client_action_id);
      }

      if (result.state) {
        await cacheStateInIDB(result.state);
        await renderTasksFromIDB(currentFilterState);
      }

      isActuallyOffline = false;
      await updateUIBadges();
    } else {
      isActuallyOffline = true;
      await updateUIBadges();
    }
  } catch (error) {
    logDebug('⚠️', 'Error al resincronizar red:', error.message);
    isActuallyOffline = true;
    await updateUIBadges();
  } finally {
    isSyncing = false;
  }
}

// 9. Actualización de Badges de Estado y Banner de Sincronización
async function updateUIBadges() {
  const statusBadge = document.getElementById('connection-status-badge');
  const syncBanner = document.getElementById('sync-banner');
  const syncCountSpan = document.getElementById('sync-count');

  const queue = await idbGetAll('offline_queue');
  const pendingCount = (queue && queue.length) ? queue.length : 0;
  const isOnline = navigator.onLine && !isActuallyOffline;

  if (statusBadge) {
    if (isOnline && pendingCount === 0) {
      statusBadge.textContent = '● En Línea';
      statusBadge.className = 'badge badge-agro';
    } else if (isOnline && pendingCount > 0) {
      statusBadge.textContent = `● En Línea (${pendingCount} Pendientes)`;
      statusBadge.className = 'badge badge-amber';
    } else {
      statusBadge.textContent = '📡 Sin Conexión (Modo Offline)';
      statusBadge.className = 'badge badge-amber';
    }
  }

  if (syncBanner) {
    if (pendingCount > 0) {
      syncBanner.classList.remove('hidden');
      if (syncCountSpan) syncCountSpan.textContent = pendingCount;
    } else {
      syncBanner.classList.add('hidden');
    }
  }
}

// 10. Cargar e Hidratar Estado Fresco desde API (Solo Online)
async function fetchAndCacheState() {
  if (navigator.onLine) {
    try {
      const res = await fetch('/api/campo/estado');
      if (res.ok) {
        const state = await res.json();
        await cacheStateInIDB(state);
        isActuallyOffline = false;
      } else {
        isActuallyOffline = true;
      }
    } catch (e) {
      logDebug('📡', 'Detección offline por fallo de fetch:', e.message);
      isActuallyOffline = true;
    }
    await updateUIBadges();
  }
}

// 11. Intercepción Robusta e Incondicional de Formularios de Campo
function setupFormInterceptions() {
  // Listener de submit para intercepción sincrónica inmediata (CERO RELOADS / CERO SCROLL)
  document.addEventListener('submit', (e) => {
    const form = e.target;
    const actionAttr = form.getAttribute('action') || form.action || '';

    let tipo = null;
    let payload = {};

    if (actionAttr.includes('/campo/acciones/lluvia')) {
      tipo = 'registrar_lluvia';
      const formData = new FormData(form);
      payload = {
        campo_id: formData.get('campo_id'),
        lote_id: formData.get('lote_id'),
        milimetros: parseFloat(formData.get('milimetros') || 0),
        observaciones: formData.get('observaciones') || ''
      };
    } else if (actionAttr.includes('/campo/acciones/incidencia')) {
      tipo = 'registrar_incidencia';
      const formData = new FormData(form);
      payload = {
        campo_id: formData.get('campo_id'),
        lote_id: formData.get('lote_id'),
        titulo: formData.get('titulo'),
        prioridad: formData.get('prioridad'),
        observaciones: formData.get('observaciones') || ''
      };
    } else if (actionAttr.includes('/campo/acciones/stock')) {
      tipo = 'movimiento_stock';
      const formData = new FormData(form);
      payload = {
        campo_id: formData.get('campo_id'),
        insumo: formData.get('insumo'),
        cantidad: parseFloat(formData.get('cantidad') || 0),
        unidad: formData.get('unidad'),
        observaciones: formData.get('observaciones') || ''
      };
    } else if (actionAttr.includes('/campo/tareas/nueva')) {
      tipo = 'nueva_labor';
      const formData = new FormData(form);
      payload = {
        campo_id: formData.get('campo_id'),
        lote_id: formData.get('lote_id'),
        tipo: formData.get('tipo'),
        titulo: formData.get('titulo'),
        responsable: formData.get('responsable'),
        prioridad: formData.get('prioridad'),
        observaciones: formData.get('observaciones') || ''
      };
    } else {
      const iniciarMatch = actionAttr.match(/\/campo\/tareas\/([^\/]+)\/iniciar/);
      const completarMatch = actionAttr.match(/\/campo\/tareas\/([^\/]+)\/completar/);

      if (iniciarMatch) {
        tipo = 'iniciar_labor';
        payload = { tarea_id: iniciarMatch[1] };
      } else if (completarMatch) {
        tipo = 'completar_tarea';
        payload = { tarea_id: completarMatch[1] };
      }
    }

    if (tipo) {
      // PREVENT DEFAULT & STOP PROPAGATION INMEDIATO Y SINCRÓNICO (EVITA SCROLL Y RECARGA)
      e.preventDefault();
      e.stopPropagation();

      logDebug('📌', 'Listener submit capturado', { actionAttr, tipo });
      logDebug('🛑', 'preventDefault() ejecutado sincrónicamente.');

      if (form.closest('details')) {
        form.closest('details').removeAttribute('open');
      }
      form.reset();

      // Procesar acción de forma asíncrona de manera fluida
      processFieldAction(tipo, payload);
    }
  });

  // Listener de clic en filtros de pestañas (Offline-compatible sin recarga)
  document.addEventListener('click', async (e) => {
    const pill = e.target.closest('.pill-filter');
    if (pill) {
      e.preventDefault();
      const href = pill.getAttribute('href') || '';
      let filterParam = 'todas';
      if (href.includes('estado_filtro=')) {
        filterParam = href.split('estado_filtro=')[1];
      }

      document.querySelectorAll('.pill-filter').forEach((p) => p.className = 'pill-filter');
      if (filterParam === 'pendiente') pill.className = 'pill-filter active-pending';
      else if (filterParam === 'en_curso') pill.className = 'pill-filter active-in-progress';
      else if (filterParam === 'hecha') pill.className = 'pill-filter active-done';
      else pill.className = 'pill-filter active';

      await renderTasksFromIDB(filterParam);
    }
  });
}

// 12. Inicialización Global
window.addEventListener('DOMContentLoaded', async () => {
  logDebug('🚀', 'Inicializando Engine Offline de Modo Campo...');
  await openOfflineDB();
  setupFormInterceptions();

  await seedIDBFromSSRHtml();

  if (navigator.onLine) {
    await fetchAndCacheState();
    await syncOfflineQueue();
  } else {
    isActuallyOffline = true;
  }

  await updateUIBadges();
  await renderTasksFromIDB('todas');

  const btnSync = document.getElementById('btn-sync-now');
  if (btnSync) {
    btnSync.addEventListener('click', async () => {
      logDebug('🔄', 'Sincronización manual solicitada por el usuario');
      await syncOfflineQueue();
    });
  }

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js', { scope: '/' })
      .then((reg) => logDebug('⚙️', 'Service Worker activo en scope:', reg.scope))
      .catch((err) => logDebug('⚠️', 'Error Service Worker:', err.message));

    navigator.serviceWorker.addEventListener('message', (event) => {
      if (event.data && event.data.type === 'TRIGGER_SYNC') {
        syncOfflineQueue();
      }
    });
  }
});

window.addEventListener('online', () => {
  logDebug('📡', 'Evento window.online detectado');
  isActuallyOffline = false;
  updateUIBadges();
  syncOfflineQueue();
});

window.addEventListener('offline', () => {
  logDebug('📡', 'Evento window.offline detectado');
  isActuallyOffline = true;
  updateUIBadges();
});
