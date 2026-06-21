// Thin REST client. Every call returns parsed JSON or throws Error(detail).

async function request(method, url, body, isForm = false) {
  const opts = { method };
  if (body !== undefined) {
    if (isForm) {
      opts.body = body; // FormData; let the browser set the boundary
    } else {
      opts.headers = { "Content-Type": "application/json" };
      opts.body = JSON.stringify(body);
    }
  }
  const res = await fetch(url, opts);
  let data = null;
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    const detail = (data && (data.detail || data.message)) || `${res.status} ${res.statusText}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  bootstrap:    ()        => request("GET",  "/api/bootstrap"),
  voices:       ()        => request("GET",  "/api/voices"),

  saveEmotion:  (e)       => request("POST", "/api/emotions", e),
  deleteEmotion:(id)      => request("DELETE", `/api/emotions/${encodeURIComponent(id)}`),

  preview:      (p)       => request("POST", "/api/preview", p),
  synthesize:   (p)       => request("POST", "/api/synthesize", p),

  getSettings:  ()        => request("GET",  "/api/settings"),
  saveSettings: (patch)   => request("POST", "/api/settings", patch),

  models:       ()        => request("GET",  "/api/models"),
  uploadModels: (form)    => request("POST", "/api/models/upload", form, true),
  selectModel:  (name)    => request("POST", "/api/models/select", { name }),
  deleteModel:  (name)    => request("DELETE", `/api/models/${encodeURIComponent(name)}`),

  getColors:    ()        => request("GET",  "/api/colors"),
  putColors:    (colors)  => request("PUT",  "/api/colors", { colors }),
  exportConfig: ()        => request("GET",  "/api/config/export"),
  importConfig: (cfg)     => request("POST", "/api/config/import", cfg),
};
