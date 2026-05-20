// ============================================
// INVENTARIO ASAMBLEA DE CALDAS - Frontend
// ============================================

const API = "";
let catalogos = null;
let activoActual = null;
let registroActual = null;
let searchTimeout = null;
let acSelectedIndex = -1;

// === INIT ===
document.addEventListener("DOMContentLoaded", async () => {
  await cargarCatalogos();
  initTabs();
  initSearch();
  initPhotoCapture();
  cargarDashboard();
  
  // Boton nuevo elemento
  const btnNuevo = document.getElementById("btn-nuevo-elemento");
  if (btnNuevo) {
    btnNuevo.addEventListener("click", nuevoElementoInventario);
  }
});

// === CATALOGOS ===
async function cargarCatalogos() {
  try {
    const res = await fetch(`${API}/api/catalogos`);
    catalogos = await res.json();
    poblarSelects();
  } catch (e) {
    toast("Error cargando catálogos", "error");
  }
}

function poblarSelects() {
  if (!catalogos) return;

  const ef = document.getElementById("estado_fisico");
  if (ef) {
    ef.innerHTML = '<option value="">-- Seleccionar --</option>';
    catalogos.estados_fisicos.forEach((e) => {
      ef.innerHTML += `<option value="${e}">${e}</option>`;
    });
  }

  const ea = document.getElementById("estado_avance");
  if (ea) {
    ea.innerHTML = '<option value="">-- Seleccionar --</option>';
    catalogos.estados_avance.forEach((e) => {
      ea.innerHTML += `<option value="${e}">${e}</option>`;
    });
  }

  const acc = document.getElementById("accion_requerida");
  if (acc) {
    acc.innerHTML = '<option value="">-- Se genera automaticamente --</option>';
    catalogos.acciones.forEach((a) => {
      acc.innerHTML += `<option value="${a}">${a}</option>`;
    });
    acc.disabled = true;
  }

  // Selector grupo actual (precargado al seleccionar activo)
  const ga = document.getElementById("grupo_actual");
  if (ga && catalogos.grupos_homogeneos) {
    ga.innerHTML = '<option value="">-- Sin grupo --</option>';
    catalogos.grupos_homogeneos.forEach((g) => {
      ga.innerHTML += `<option value="${g.id}">${g.nombre}</option>`;
    });
  }

  // Selector para cambiar grupo
  const gc = document.getElementById("grupo_cambio");
  if (gc && catalogos.grupos_homogeneos) {
    gc.innerHTML = '<option value="">-- Seleccionar --</option>';
    catalogos.grupos_homogeneos.forEach((g) => {
      gc.innerHTML += `<option value="${g.id}">${g.nombre}</option>`;
    });
  }

  // Filtros del listado
  const fg = document.getElementById("filtro_grupo");
  if (fg && catalogos.grupos_homogeneos) {
    fg.innerHTML = '<option value="">Todos los grupos</option>';
    catalogos.grupos_homogeneos.forEach((g) => {
      fg.innerHTML += `<option value="${g.codigo}">${g.nombre}</option>`;
    });
  }

  const fe = document.getElementById("filtro_estado");
  if (fe) {
    fe.innerHTML = '<option value="">Todos los estados</option>';
    catalogos.estados_fisicos.forEach((e) => {
      fe.innerHTML += `<option value="${e}">${e}</option>`;
    });
  }

  const fa = document.getElementById("filtro_avance");
  if (fa) {
    fa.innerHTML = '<option value="">Todo avance</option>';
    catalogos.estados_avance.forEach((e) => {
      fa.innerHTML += `<option value="${e}">${e}</option>`;
    });
  }
}

// === TABS ===
function initTabs() {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
      btn.classList.add("active");
      const target = document.getElementById(btn.dataset.tab);
      if (target) target.classList.add("active");

      if (btn.dataset.tab === "tab-dashboard") cargarDashboard();
      if (btn.dataset.tab === "tab-listado") cargarListado(1);
    });
  });
}

// === SEARCH + AUTOCOMPLETE ===
function initSearch() {
  const input = document.getElementById("search-input");
  const list = document.getElementById("autocomplete-list");

  if (!input || !list) return;

  input.addEventListener("input", (e) => {
    const q = e.target.value.trim();
    clearTimeout(searchTimeout);
    acSelectedIndex = -1;

    if (q.length < 1) {
      list.classList.remove("show");
      return;
    }

    searchTimeout = setTimeout(() => buscarActivos(q), 250);
  });

  input.addEventListener("keydown", (e) => {
    const items = list.querySelectorAll(".ac-item");
    if (!items.length) return;

    if (e.key === "ArrowDown") {
      e.preventDefault();
      acSelectedIndex = Math.min(acSelectedIndex + 1, items.length - 1);
      updateAcSelection(items);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      acSelectedIndex = Math.max(acSelectedIndex - 1, 0);
      updateAcSelection(items);
    } else if (e.key === "Enter" && acSelectedIndex >= 0) {
      e.preventDefault();
      items[acSelectedIndex].click();
    } else if (e.key === "Escape") {
      list.classList.remove("show");
    }
  });

  document.addEventListener("click", (e) => {
    if (!e.target.closest(".search-box")) {
      list.classList.remove("show");
    }
  });
}

function updateAcSelection(items) {
  items.forEach((item, i) => {
    item.classList.toggle("selected", i === acSelectedIndex);
  });
  if (acSelectedIndex >= 0) {
    items[acSelectedIndex].scrollIntoView({ block: "nearest" });
  }
}

async function buscarActivos(q) {
  const list = document.getElementById("autocomplete-list");
  try {
    const res = await fetch(`${API}/api/activos/buscar?q=${encodeURIComponent(q)}&limit=15`);
    const activos = await res.json();

    if (!activos.length) {
      list.innerHTML = '<div class="ac-item"><span class="ac-name">No se encontraron resultados</span></div>';
      list.classList.add("show");
      return;
    }

    list.innerHTML = activos
      .map(
        (a) => `
      <div class="ac-item" data-id="${a.id}" onclick="seleccionarActivo(${a.id})">
        <div class="ac-code">${a.codigo}${a.codigo_alterno ? " | " + a.codigo_alterno : ""}</div>
        <div class="ac-name">${a.nombre}</div>
        <div class="ac-meta">${a.grupo_nombre || ""} ${a.ubicacion ? "- " + a.ubicacion : ""} ${a.costo_historico ? "- $" + formatNumber(a.costo_historico) : ""}</div>
      </div>
    `
      )
      .join("");

    list.classList.add("show");
  } catch (e) {
    console.error("Error buscando:", e);
  }
}

async function seleccionarActivo(id) {
  const list = document.getElementById("autocomplete-list");
  const input = document.getElementById("search-input");
  list.classList.remove("show");
  showLoading(true);

  try {
    const res = await fetch(`${API}/api/activos/${id}`);
    if (!res.ok) throw new Error("Activo no encontrado");

    const data = await res.json();
    activoActual = data.activo;
    registroActual = data.registro;

    input.value = `${activoActual.codigo} - ${activoActual.nombre}`;
    mostrarInfoActivo();
    llenarFormulario();
  } catch (e) {
    toast("Error cargando activo", "error");
  } finally {
    showLoading(false);
  }
}

function mostrarInfoActivo() {
  const container = document.getElementById("activo-info");
  if (!container || !activoActual) return;

  container.classList.add("show");
  document.getElementById("info-codigo").textContent = activoActual.codigo;
  document.getElementById("info-alterno").textContent = activoActual.codigo_alterno || "-";
  document.getElementById("info-nombre").textContent = activoActual.nombre;
  document.getElementById("info-tipo").textContent = activoActual.tipo || "-";
  document.getElementById("info-grupo").textContent = activoActual.grupo_nombre || "-";
  document.getElementById("info-cuenta").textContent = activoActual.cuenta_activo || "-";
  document.getElementById("info-costo").textContent = activoActual.costo_historico ? "$" + formatNumber(activoActual.costo_historico) : "-";
  document.getElementById("info-vida-util").textContent = activoActual.vida_util_meses ? activoActual.vida_util_meses + " meses" : "-";
  document.getElementById("info-ubicacion").textContent = activoActual.ubicacion || "-";
  document.getElementById("info-proveedor").textContent = activoActual.proveedor || "-";

  // Status badge
  const statusBadge = document.getElementById("info-status");
  if (registroActual) {
    statusBadge.className = "badge badge-success";
    statusBadge.textContent = "Inventariado";
  } else {
    statusBadge.className = "badge badge-warning";
    statusBadge.textContent = "Pendiente";
  }
}

function llenarFormulario() {
  // Cargar grupo actual del activo
  if (activoActual.grupo_homogeneo_id) {
    const ga = document.getElementById("grupo_actual");
    if (ga) {
      const exists = Array.from(ga.options).some(o => o.value === String(activoActual.grupo_homogeneo_id));
      if (!exists) {
        // Si el select no contiene el grupo (precarga fallida), lo agregamos dinámicamente
        const opt = document.createElement('option');
        opt.value = String(activoActual.grupo_homogeneo_id);
        opt.textContent = activoActual.grupo_nombre || `Grupo ${activoActual.grupo_homogeneo_id}`;
        ga.appendChild(opt);
      }
      setVal("grupo_actual", activoActual.grupo_homogeneo_id);
    }
  }

  // Prellenar costo y vida útil del activo (Excel)
  document.getElementById("costo_verificado").value = activoActual.costo_historico || "";
  document.getElementById("vida_util_verificada").value = activoActual.vida_util_meses || "";

  if (!registroActual) {
    limpiarFormularioRegistro();
    // Limpiar foto preview
    limpiarFoto();
    return;
  }

  const r = registroActual;
  setVal("estado_fisico", r.estado_fisico);
  setChecked("existe_fisicamente", r.existe_fisicamente);
  setVal("costo_verificado", r.costo_verificado || activoActual.costo_historico || "");
  setVal("vida_util_verificada", r.vida_util_verificada || activoActual.vida_util_meses || "");
  setVal("custodio_responsable", r.custodio_responsable);
  setVal("ubicacion_verificada", r.ubicacion_verificada);
  setVal("accion_requerida", r.accion_requerida);
  setVal("motivo_accion", r.motivo_accion);
  setVal("estado_avance", r.estado_avance);
  setVal("observaciones", r.observaciones);
  setVal("verificado_por", r.verificado_por);

  // Foto existente
  const preview = document.getElementById("photo-preview");
  if (r.foto_url) {
    mostrarFotoPreview(r.foto_url);
  } else {
    preview.innerHTML = '<div class="placeholder"><span class="icon">&#128247;</span>Toca para tomar foto<br>o seleccionar imagen</div>';
  }
}

function limpiarFormularioRegistro() {
  ["estado_fisico", "custodio_responsable", "ubicacion_verificada",
   "accion_requerida", "motivo_accion", "observaciones", "verificado_por", "razon_cambio"
  ].forEach(id => setVal(id, ""));

  setVal("estado_avance", "No verificado");
  setVal("grupo_cambio", "");
  setChecked("existe_fisicamente", false);

  const preview = document.getElementById("photo-preview");
  if (preview) {
    preview.innerHTML = '<div class="placeholder"><span class="icon">&#128247;</span>Toca para tomar foto<br>o seleccionar imagen</div>';
  }
}

// === PHOTO CAPTURE ===
function initPhotoCapture() {
  const preview = document.getElementById("photo-preview");
  const fileInput = document.getElementById("foto-input");

  if (!preview || !fileInput) return;

  preview.addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      preview.innerHTML = `<img src="${ev.target.result}" alt="Preview">`;
    };
    reader.readAsDataURL(file);
  });
}

function tomarFotoBtn() {
  const fileInput = document.getElementById("foto-input");
  if (fileInput) {
    fileInput.setAttribute("capture", "environment");
    fileInput.click();
    fileInput.removeAttribute("capture");
  }
}

function seleccionarFotoBtn() {
  const fileInput = document.getElementById("foto-input");
  if (fileInput) {
    fileInput.removeAttribute("capture");
    fileInput.click();
  }
}

// === FOTOS ===
function mostrarFotoPreview(url) {
  const preview = document.getElementById("photo-preview");
  const btnLimpiar = document.getElementById("btn-limpiar-foto");
  preview.innerHTML = `<img src="${url}" alt="Preview" style="max-width:100%;max-height:300px;border-radius:var(--radius);">`;
  if (btnLimpiar) btnLimpiar.style.display = "inline-block";
}

function limpiarFoto() {
  const preview = document.getElementById("photo-preview");
  const fileInput = document.getElementById("foto-input");
  const btnLimpiar = document.getElementById("btn-limpiar-foto");
  
  preview.innerHTML = `
    <div class="placeholder">
      <span class="icon">&#128247;</span>
      Toca para tomar foto<br>o seleccionar imagen
    </div>
  `;
  if (fileInput) fileInput.value = "";
  if (btnLimpiar) btnLimpiar.style.display = "none";
}

// === GRUPO ===
function mostrarSelectorGrupo() {
  document.getElementById("selector-grupo-nuevo").style.display = "block";
}

function cancelarCambioGrupo() {
  document.getElementById("selector-grupo-nuevo").style.display = "none";
  document.getElementById("grupo_cambio").value = "";
  document.getElementById("razon_cambio").value = "";
}

// === SAVE ===
async function guardarRegistro() {
  if (!activoActual) {
    toast("Primero busca y selecciona un activo", "error");
    return;
  }

  const form = new FormData();
  form.append("activo_id", activoActual.id);
  
  const estadoFisico = getVal("estado_fisico");
  if (estadoFisico) form.append("estado_fisico", estadoFisico);
  
  // Solo enviar existe_fisicamente cuando es relevante:
  // - Si ya existe un registro, siempre enviamos el estado (permite desmarcar).
  // - Si es un registro nuevo, enviamos solo si está marcado para evitar sobrescribir con 'false' por defecto.
  const existeCheckbox = document.getElementById("existe_fisicamente");
  const existeChecked = !!(existeCheckbox && existeCheckbox.checked);
  if (registroActual) {
    form.append("existe_fisicamente", existeChecked ? "true" : "false");
  } else if (existeChecked) {
    form.append("existe_fisicamente", "true");
  }

  const costoVal = getVal("costo_verificado");
  const vuVal = getVal("vida_util_verificada");
  if (costoVal) form.append("costo_verificado", costoVal);
  if (vuVal) form.append("vida_util_verificada", vuVal);

  ["custodio_responsable", "ubicacion_verificada", "accion_requerida", "estado_avance",
   "observaciones", "verificado_por", "soporte_documental"
  ].forEach(field => {
    const val = getVal(field);
    if (val) form.append(field, val);
  });

  // Foto
  const fileInput = document.getElementById("foto-input");
  if (fileInput?.files[0]) {
    form.append("foto", fileInput.files[0]);
  }

  showLoading(true);
  try {
    const res = await fetch(`${API}/api/registros`, { method: "POST", body: form });
    if (!res.ok) {
      const errMsg = await safeJsonError(res);
      throw new Error(errMsg);
    }

    registroActual = await res.json();
    mostrarInfoActivo();
    toast("✅ Registro guardado", "success");

    // Limpiar file input
    if (fileInput) fileInput.value = "";

    // Auto-limpiar en 2 segundos y permitir siguiente registro
    setTimeout(() => {
      nuevoRegistro();
      toast("💡 Selecciona otro código para continuar", "info");
    }, 2000);
  } catch (e) {
    toast(e.message || "Error al guardar registro", "error");
  } finally {
    showLoading(false);
  }
}

function nuevoRegistro() {
  activoActual = null;
  registroActual = null;
  document.getElementById("search-input").value = "";
  document.getElementById("activo-info").classList.remove("show");
  limpiarFormularioRegistro();
  document.getElementById("costo_verificado").value = "";
  document.getElementById("vida_util_verificada").value = "";
  document.getElementById("search-input").focus();
}

// === DASHBOARD ===
let dashboardPollingInterval = null;

async function cargarDashboard() {
  await actualizarDashboard();
  
  // Polling: actualizar cada 5 segundos
  if (dashboardPollingInterval) clearInterval(dashboardPollingInterval);
  dashboardPollingInterval = setInterval(actualizarDashboard, 5000);
}

async function actualizarDashboard() {
  try {
    const res = await fetch(`${API}/api/dashboard`);
    const data = await res.json();

    document.getElementById("dash-total").textContent = data.total_activos;
    document.getElementById("dash-inventariados").textContent = data.inventariados;
    document.getElementById("dash-pendientes").textContent = data.pendientes;
    document.getElementById("dash-porcentaje").textContent = data.porcentaje_avance + "%";

    // Progress bar
    document.getElementById("progress-fill").style.width = data.porcentaje_avance + "%";
    document.getElementById("progress-text").textContent =
      `${data.inventariados} de ${data.total_activos} activos verificados`;

    // Charts
    renderBarChart("chart-estados", data.por_estado_fisico, data.inventariados);
    renderBarChart("chart-grupos", data.por_grupo, data.total_activos);
    renderBarChart("chart-avance", data.por_estado_avance, data.inventariados);

    // Cargar estadísticas por usuario
    await cargarEstadisticasUsuarios();
  } catch (e) {
    console.error("Error dashboard:", e);
  }
}

async function cargarEstadisticasUsuarios() {
  try {
    const res = await fetch(`${API}/api/dashboard/por-usuario`);
    if (!res.ok) return;
    
    const usuarios = await res.json();
    const tbody = document.getElementById("usuarios-tbody");
    if (!tbody) return;

    if (usuarios.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" class="td-empty">Sin registros aún</td></tr>';
      return;
    }

    tbody.innerHTML = usuarios
      .map((u, i) => `
        <tr>
          <td>${i + 1}.</td>
          <td><strong>${u.verificado_por || "Sin nombre"}</strong></td>
          <td class="td-right"><span class="badge badge-success">${u.cantidad}✓</span></td>
        </tr>
      `)
      .join("");
  } catch (e) {
    console.error("Error cargando usuarios:", e);
  }
}

function renderBarChart(containerId, data, total) {
  const container = document.getElementById(containerId);
  if (!container) return;

  const colors = ["#3b82f6", "#059669", "#d97706", "#dc2626", "#8b5cf6", "#ec4899", "#06b6d4", "#84cc16"];
  const entries = Object.entries(data).sort((a, b) => b[1] - a[1]);

  if (!entries.length) {
    container.innerHTML = '<div class="empty-state"><p>Sin datos aún</p></div>';
    return;
  }

  const maxVal = Math.max(...entries.map(([, v]) => v));

  container.innerHTML = entries
    .map(
      ([name, count], i) => `
    <div class="chart-bar-container">
      <div class="chart-bar-label">
        <span class="name">${name}</span>
        <span class="count">${count}</span>
      </div>
      <div class="chart-bar-track">
        <div class="chart-bar-fill" style="width: ${(count / maxVal) * 100}%; background: ${colors[i % colors.length]}"></div>
      </div>
    </div>
  `
    )
    .join("");
}

// === LISTADO (tabla tipo Excel) ===
let listadoPage = 1;
let filtroTimeout = null;

function filtroListadoDebounce() {
  clearTimeout(filtroTimeout);
  filtroTimeout = setTimeout(() => cargarListado(1), 300);
}

async function cargarListado(page = 1) {
  listadoPage = page;
  const grupo = document.getElementById("filtro_grupo")?.value || "";
  const estado = document.getElementById("filtro_estado")?.value || "";
  const avance = document.getElementById("filtro_avance")?.value || "";
  const pendientes = document.getElementById("filtro_pendientes")?.checked || false;
  const buscar = document.getElementById("filtro_buscar")?.value.trim() || "";

  try {
    let url = `${API}/api/activos?page=${page}&size=50`;
    if (grupo) url += `&grupo=${encodeURIComponent(grupo)}`;
    if (estado) url += `&estado=${encodeURIComponent(estado)}`;
    if (avance) url += `&estado_avance=${encodeURIComponent(avance)}`;
    if (pendientes) url += `&solo_pendientes=true`;
    if (buscar) url += `&q=${encodeURIComponent(buscar)}`;

    const res = await fetch(url);
    const data = await res.json();

    const tbody = document.getElementById("listado-tbody");
    const countEl = document.getElementById("listado-count");

    if (!data.items.length) {
      tbody.innerHTML = '<tr><td colspan="10" class="td-empty">No se encontraron activos con estos filtros</td></tr>';
      countEl.textContent = "0 registros";
      document.getElementById("listado-pagination").innerHTML = "";
      return;
    }

    tbody.innerHTML = data.items
      .map((item) => {
        const estadoBadge = item.estado_fisico
          ? `<span class="badge badge-info">${item.estado_fisico}</span>`
          : '<span style="color:var(--gray-300)">—</span>';
        const avanceBadge = item.inventariado
          ? `<span class="badge ${item.estado_avance === 'Cerrado' ? 'badge-success' : 'badge-warning'}">${item.estado_avance || 'Registrado'}</span>`
          : '<span class="badge badge-gray">Pendiente</span>';
        const fotoCell = item.foto_url
          ? `<img src="${item.foto_url}" alt="">`
          : '<span class="no-foto">—</span>';

        return `
        <tr onclick="irAActivo(${item.id})">
          <td class="td-code">${item.codigo}</td>
          <td class="td-name" title="${item.nombre}">${item.nombre}</td>
          <td>${item.grupo_nombre || '—'}</td>
          <td class="td-costo">${item.costo_historico ? '$' + formatNumber(item.costo_historico) : '—'}</td>
          <td style="text-align:center">${item.vida_util_meses || '—'}</td>
          <td>${estadoBadge}</td>
          <td>${avanceBadge}</td>
          <td>${item.custodio || '—'}</td>
          <td>${item.ubicacion_verificada || item.ubicacion || '—'}</td>
          <td class="td-foto">${fotoCell}</td>
        </tr>`;
      })
      .join("");

    countEl.textContent = `${data.total} registros — pág ${page}/${data.pages}`;

    // Paginacion
    const pag = document.getElementById("listado-pagination");
    pag.innerHTML = `
      <button onclick="cargarListado(${page - 1})" ${page <= 1 ? "disabled" : ""}>&#9664;</button>
      <span class="page-info">${page} / ${data.pages}</span>
      <button onclick="cargarListado(${page + 1})" ${page >= data.pages ? "disabled" : ""}>&#9654;</button>
    `;
  } catch (e) {
    console.error("Error listado:", e);
  }
}

function irAActivo(id) {
  // Cambiar a tab registro y cargar el activo
  document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
  document.querySelector('[data-tab="tab-registro"]').classList.add("active");
  document.getElementById("tab-registro").classList.add("active");
  seleccionarActivo(id);
}

// === UTILITIES ===
async function safeJsonError(res) {
  try {
    const data = await res.json();
    return data.detail || JSON.stringify(data);
  } catch {
    const text = await res.text();
    return `Error del servidor (${res.status}): ${text.substring(0, 150)}`;
  }
}

function setVal(id, val) {
  const el = document.getElementById(id);
  if (el) el.value = val || "";
}

function getVal(id) {
  const el = document.getElementById(id);
  return el ? el.value.trim() : "";
}

function setChecked(id, val) {
  const el = document.getElementById(id);
  if (el) el.checked = !!val;
}

// === CAMBIO DE GRUPO Y ACCIONES ===
async function cambiarGrupo() {
  if (!activoActual) {
    toast("Primero busca y selecciona un activo", "error");
    return;
  }

  const grupoId = getVal("grupo_cambio");
  if (!grupoId) {
    toast("Selecciona un grupo", "error");
    return;
  }

  if (parseInt(grupoId) === activoActual.grupo_homogeneo_id) {
    toast("El activo ya pertenece a este grupo", "info");
    return;
  }

  const razonCambio = getVal("razon_cambio");
  
  const form = new FormData();
  form.append("grupo_homogeneo_id", grupoId);
  if (razonCambio) form.append("razon_cambio", razonCambio);
  form.append("modificado_por", getVal("verificado_por") || "Usuario");

  showLoading(true);
  try {
    const res = await fetch(`${API}/api/activos/${activoActual.id}/grupo`, {
      method: "PATCH",
      body: form
    });
    if (!res.ok) {
      const errMsg = await safeJsonError(res);
      throw new Error(errMsg);
    }

    const result = await res.json();
    
    // Recargar la informacion del activo
    const acRes = await fetch(`${API}/api/activos/${activoActual.id}`);
    const acData = await acRes.json();
    activoActual = acData.activo;
    registroActual = acData.registro;
    
    mostrarInfoActivo();
    llenarFormulario();
    
    toast(`Grupo cambiado de "${result.grupo_anterior_nombre}" a "${result.grupo_nuevo_nombre}"`, "success");
    
    setVal("grupo_cambio", "");
    setVal("razon_cambio", "");
  } catch (e) {
    toast(e.message || "Error al cambiar grupo", "error");
  } finally {
    showLoading(false);
  }
}

async function nuevoElementoInventario() {
  const respuesta = prompt("Ingresa el codigo del nuevo activo a crear (se abrira el formulario de inventario):");
  if (!respuesta) return;
  
  toast("Funcionalidad de crear nuevo elemento próximamente disponible", "info");
  // Aqui iria la lógica para crear un nuevo elemento
  // Por ahora, solo mostramos un mensaje informativo
}

function formatNumber(n) {
  if (n == null) return "";
  return new Intl.NumberFormat("es-CO").format(n);
}

function toast(msg, type = "info") {
  let t = document.getElementById("toast");
  if (!t) {
    t = document.createElement("div");
    t.id = "toast";
    t.className = "toast";
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => t.classList.remove("show"), 3000);
}

function showLoading(show) {
  const overlay = document.getElementById("loading-overlay");
  if (overlay) overlay.classList.toggle("show", show);
}
