export async function postJson<T>(url: string, body: unknown): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function adminFetchJson<T>(url: string, token: string): Promise<T> {
  const response = await fetch(url, { headers: { "X-Admin-Token": token } });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function adminPostJson<T>(url: string, body: unknown, token: string): Promise<T> {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Admin-Token": token },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function adminDeleteJson<T = { message?: string }>(url: string, token: string): Promise<T> {
  const response = await fetch(url, { method: "DELETE", headers: { "X-Admin-Token": token } });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

async function readError(response: Response) {
  try {
    const data = (await response.json()) as { detail?: string };
    return data.detail || "请求失败";
  } catch {
    return `请求失败（HTTP ${response.status}）`;
  }
}
