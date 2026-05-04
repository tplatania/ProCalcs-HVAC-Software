// Shared header builder for cross-service calls into procalcs-bom (and
// any other ProCalcs Flask service that follows the same auth pattern).
//
// Three header families:
//   - X-Procalcs-Service-Token    : shared secret, gates the upstream
//   - X-Client-Id                 : attribution for upstream logs
//   - X-Procalcs-User-Email/Name  : OAuth-verified user identity, lets
//                                   upstream JIT-upsert a User row and
//                                   make billing decisions per-user
//
// The user-identity headers are optional; if requireAuth hasn't run on
// this route (e.g. health probes), they're omitted and upstream stays
// in its existing behavior. Anywhere we want billing to be live, the
// route must be downstream of requireAuth so req.user is populated.

import type { Request } from "express";
import { config } from "./config.js";

export function buildUpstreamHeaders(req?: Request): Record<string, string> {
  const headers: Record<string, string> = {
    "X-Client-Id": config.clientId,
  };
  if (config.serviceSharedSecret) {
    headers["X-Procalcs-Service-Token"] = config.serviceSharedSecret;
  }
  if (req?.user?.email) {
    headers["X-Procalcs-User-Email"] = req.user.email;
    if (req.user.name) {
      headers["X-Procalcs-User-Name"] = req.user.name;
    }
  }
  return headers;
}
