import type { Configuration } from "@azure/msal-browser";

const tenantId = import.meta.env.VITE_ENTRA_TENANT_ID as string;
const spaClientId = import.meta.env.VITE_ENTRA_SPA_CLIENT_ID as string;
const apiClientId = import.meta.env.VITE_API_CLIENT_ID as string;

export const msalConfig: Configuration = {
  auth: {
    clientId: spaClientId,
    authority: `https://login.microsoftonline.com/${tenantId}`,
    redirectUri: "/",
  },
  cache: {
    cacheLocation: "sessionStorage",
  },
};

// Scope on the API's own app registration — this is the token the API
// validates as the caller's identity, and later exchanges via On-Behalf-Of
// for a separate Graph-scoped token. It is NOT a Graph scope itself.
export const apiLoginRequest = {
  scopes: [`api://${apiClientId}/access_as_user`],
};

export const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000";
