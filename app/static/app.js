"use strict";

const STATE_LABELS = {
  pending: "En cola…",
  processing: "Generando audio…",
  done: "Listo",
  error: "Error",
};

function renderRow(wrap, data) {
  wrap.dataset.status = data.status;
  wrap.querySelector(".result-name").textContent = data.source_name;
  const state = wrap.querySelector(".result-state");
  state.textContent = data.error ? data.error : STATE_LABELS[data.status] || data.status;
  state.style.color = data.status === "error" ? "var(--error)" : "var(--muted)";
  wrap.querySelector(".bar > span").style.width = Math.round(data.progress * 100) + "%";

  const dl = wrap.querySelector(".btn-download");
  let audio = wrap.querySelector("audio");
  if (data.download_url) {
    dl.href = data.download_url;
    dl.hidden = false;
    if (!audio) {
      audio = document.createElement("audio");
      audio.controls = true;
      audio.preload = "none";
      wrap.appendChild(audio);
    }
    if (audio.getAttribute("src") !== data.download_url) audio.src = data.download_url;
    addMusicAndSpeed(wrap, data.music_download_url);
  } else {
    dl.hidden = true;
    if (audio) audio.remove();
  }
}


function attachSpeed(audio) {
  if (audio.dataset.speedReady) return;
  audio.dataset.speedReady = "yes";
  audio.preservesPitch = true;
  const label = document.createElement("label");
  label.textContent = "Velocidad de escucha ";
  const select = document.createElement("select");
  for (const rate of [0.75, 0.9, 1, 1.15, 1.25, 1.5]) {
    const option = document.createElement("option");
    option.value = rate;
    option.textContent = rate + "×";
    option.selected = rate === 1;
    select.appendChild(option);
  }
  select.addEventListener("change", () => { audio.playbackRate = Number(select.value); });
  label.appendChild(select);
  audio.after(label);
}
function addMusicAndSpeed(wrap, url) {
  const voice = wrap.querySelector("audio");
  if (voice) {
    voice.setAttribute("aria-label", "Solo voz");
    attachSpeed(voice);
  }
  if (url && !wrap.querySelector(".music-download")) {
    const section = document.createElement("div");
    const link = document.createElement("a");
    link.className = "btn-download music-download";
    link.href = url;
    link.textContent = "Descargar con música";
    const audio = document.createElement("audio");
    audio.controls = true;
    audio.preload = "none";
    audio.src = url;
    audio.setAttribute("aria-label", "Con música");
    section.append(link, audio);
    wrap.appendChild(section);
    attachSpeed(audio);
  }
}

function createRow(data) {
  const wrap = document.createElement("div");
  wrap.className = "result-row-wrap";
  wrap.dataset.jobId = data.id;
  wrap.innerHTML =
    '<div class="result-row">' +
    '<span class="result-name"></span>' +
    '<span class="result-state"></span>' +
    '<a class="btn-download" hidden>Descargar solo voz</a>' +
    "</div>" +
    '<div class="bar"><span></span></div>';
  renderRow(wrap, data);
  return wrap;
}

async function pollJob(jobId, wrap) {
  try {
    const res = await fetch(`/jobs/${jobId}`, { headers: { Accept: "application/json" } });
    if (!res.ok) return;
    const data = await res.json();
    renderRow(wrap, data);
    if (data.status === "pending" || data.status === "processing") {
      setTimeout(() => pollJob(jobId, wrap), 1000);
    }
  } catch (_e) {
    setTimeout(() => pollJob(jobId, wrap), 2500);
  }
}

document.addEventListener("DOMContentLoaded", () => {
  const $ = (id) => document.getElementById(id);
  const form = $("upload-form"), input = $("files"), dropzone = $("dropzone");
  const editor = $("script-text"), mode = $("reading-mode"), confirm = $("review-confirm");
  let draft = null, dirty = false, busy = false, adapted = "";
  const csrf = form.elements.csrf_token.value;
  const err = (id, message) => { $(id).textContent = message; $(id).hidden = !message; };
  function buttons() {
    $("generate-reviewed").disabled = !draft || dirty || busy || !confirm.checked || $("review-panel").dataset.preview === "true";
    $("save-review").disabled = !draft || busy || !editor.value.trim();
    $("submit-btn").disabled = busy;
    mode.disabled = busy;
    editor.readOnly = busy || mode.value === "literal";
    $("script-count").textContent = editor.value.length.toLocaleString("es") + " caracteres";
    $("download-script").hidden = dirty;
  }
  async function request(url, options = {}) {
    const response = await fetch(url, { ...options, headers: { Accept: "application/json", ...options.headers } });
    let data;
    try { data = await response.json(); } catch { throw new Error("No se ha podido leer la respuesta. Inténtalo de nuevo."); }
    if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Revisa los datos enviados.");
    return data;
  }
  function comparison(data) {
    $("text-diff").textContent = data.comparison.diff || "El guion coincide con el texto original.";
    const warnings = [];
    if (data.comparison.missing_numbers.length) warnings.push("Comprueba estas cifras del original: " + data.comparison.missing_numbers.join(", ") + ". Pueden haberse escrito con palabras o haberse omitido.");
    if (data.comparison.changed_quotes.length) warnings.push("Hay citas entre comillas modificadas o ausentes. Comprueba si deben mantenerse literales.");
    $("review-warnings").textContent = warnings.join(" ");
    $("review-warnings").hidden = !warnings.length;
  }
  function display(data) {
    draft = data; draft.generatedHere = data.generated; dirty = false;
    $("review-panel").hidden = false;
    $("review-source").textContent = data.source;
    $("original-text").value = data.original;
    editor.value = data.script; mode.value = data.mode;
    editor.scrollTop = 0; $("original-text").scrollTop = 0;
    adapted = data.mode === "adapted" ? data.script : "";
    if (data.audio_options) {
      $("audio-voice").value = data.audio_options[0];
      $("audio-speed").value = String(data.audio_options[1]);
      if (!$("audio-speed").value && data.audio_options[1] === 1) $("audio-speed").value = "1.0";
      $("audio-music").value = data.audio_options[2];
    }
    confirm.checked = false;
    $("download-script").href = `/reviews/${data.id}/download`;
    $("save-status").textContent = `Versión ${data.version} guardada.`;
    help(); comparison(data); buttons();
    $("review-title").focus();
  }
  function help() {
    $("mode-help").textContent = mode.value === "adapted"
      ? "Escribe o pega una versión para escuchar. El original se conserva para comparar. La adaptación no se genera automáticamente."
      : "La lectura literal conserva el texto extraído. Para corregirlo o reformularlo, elige Versión para escuchar.";
  }
  async function saved() {
    try {
      const reviews = await request("/reviews");
      $("saved-reviews").replaceChildren();
      if (!reviews.length) { $("saved-reviews").textContent = "Tus guiones aparecerán aquí al extraer un documento."; return; }
      for (const item of reviews) {
        const button = document.createElement("button");
        button.type = "button"; button.className = "saved-review";
        button.textContent = `${item.source} · ${item.mode === "adapted" ? "Para escuchar" : "Literal"} · versión ${item.version}`;
        button.addEventListener("click", async () => {
          if (busy) return;
          if (dirty) { err("review-error", "Guarda el guion actual antes de abrir otro."); return; }
          busy = true; buttons(); err("review-error", "");
          try { display(await request(`/reviews/${item.id}`)); }
          catch (e) { err("form-error", e.message); }
          finally { busy = false; buttons(); }
        });
        $("saved-reviews").appendChild(button);
      }
    } catch (e) { err("form-error", e.message); }
  }
  function changed() {
    dirty = true; confirm.checked = false;
    $("save-status").textContent = "Hay cambios sin guardar. Guarda y vuelve a confirmar la revisión.";
    buttons();
  }
  editor.addEventListener("input", changed);
  mode.addEventListener("change", () => {
    if (!draft) return;
    if (mode.value === "literal") { adapted = editor.value; editor.value = draft.original; }
    else editor.value = adapted || draft.original;
    help(); changed();
  });
  confirm.addEventListener("change", buttons);
  for (const id of ["audio-voice", "audio-speed", "audio-music"]) $(id).addEventListener("change", () => {
    // A saved revision is idempotent: save again to generate a new configuration.
    if (draft && draft.generatedHere) changed();
  });
  $("save-review").addEventListener("click", async () => {
    if (!draft || busy) return;
    busy = true; buttons(); err("review-error", "");
    try {
      const data = await request(`/reviews/${draft.id}`, { method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: draft.version, mode: mode.value, text: editor.value, csrf_token: csrf }) });
      display(data); await saved();
    } catch (e) { err("review-error", e.message); }
    finally { busy = false; buttons(); }
  });
  $("generate-reviewed").addEventListener("click", async () => {
    if (!draft || dirty || busy || !confirm.checked || $("review-panel").dataset.preview === "true") return;
    busy = true; buttons(); err("review-error", "");
    try {
      const data = await request(`/reviews/${draft.id}/generate`, { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ version: draft.version, reviewed: true, csrf_token: csrf,
          voice: $("audio-voice").value, speed: Number($("audio-speed").value), music: $("audio-music").value }) });
      $("result").hidden = false;
      let wrap = [...$("results-list").children].find((row) => row.dataset.jobId === data.id);
      if (!wrap) { wrap = createRow(data); $("results-list").prepend(wrap); }
      pollJob(data.id, wrap); draft.generatedHere = true;
      $("save-status").textContent = `Audio solicitado con la versión ${draft.version}. El guion queda guardado.`;
    } catch (e) { err("review-error", e.message); }
    finally { busy = false; buttons(); }
  });
  function files() {
    $("dz-files").replaceChildren();
    for (const f of input.files) { const chip = document.createElement("div"); chip.className = "file-chip"; chip.textContent = f.name; $("dz-files").appendChild(chip); }
  }
  input.addEventListener("change", files);
  for (const ev of ["dragenter", "dragover"]) dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.add("drag"); });
  for (const ev of ["dragleave", "drop"]) dropzone.addEventListener(ev, (e) => { e.preventDefault(); dropzone.classList.remove("drag"); });
  dropzone.addEventListener("drop", (e) => { if (!busy && e.dataTransfer?.files.length) { input.files = e.dataTransfer.files; files(); } });
  form.addEventListener("submit", async (ev) => {
    ev.preventDefault(); err("form-error", "");
    if (busy) return;
    if (dirty) { err("form-error", "Guarda el guion actual antes de cargar otro documento."); return; }
    if (!input.files.length) { err("form-error", "Selecciona al menos un documento."); return; }
    busy = true; buttons(); $("submit-btn").textContent = "Extrayendo texto…";
    try { display(await request("/upload", { method: "POST", body: new FormData(form) })); await saved(); }
    catch (e) { err("form-error", e.message); }
    finally { busy = false; $("submit-btn").textContent = "Extraer texto y revisar"; buttons(); }
  });
  window.addEventListener("beforeunload", (event) => { if (dirty) { event.preventDefault(); event.returnValue = ""; } });
  $("results-list").querySelectorAll(".result-row-wrap").forEach((wrap) => {
    addMusicAndSpeed(wrap, wrap.dataset.musicUrl);
    wrap.querySelector(".result-state").textContent = STATE_LABELS[wrap.dataset.status] || wrap.dataset.status;
    if (["pending", "processing"].includes(wrap.dataset.status)) pollJob(wrap.dataset.jobId, wrap);
  });
  saved(); buttons();
});
