export const API_URL = "/api";

export async function makePostRequest(endpoint, data) {
    const res = await fetch(`${API_URL}/${endpoint}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(data),
    });
    const json = await res.json();
    return {
    ok: res.ok,
    status: res.status,
    ...json
  };
}