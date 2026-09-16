"""zoho_sync.py — recursive Zoho WorkDrive downloader.

Downloads a Zoho WorkDrive folder tree to a local mirror. Bypasses
the Zoho UI's batch-download size cap by downloading each file
individually via the API (per-file cap doesn't stack).

Credentials: reads from ~/Procalcs/envs/zoho-workdrive.json (created
by exchanging a Zoho self-client authorization code — see
`zoho-workdrive.json` for what fields it contains). Access token
auto-refreshes as needed.

Usage:
    python3 zoho_sync.py --folder <folder_id> --dest <local_path>
                          [--dry-run] [--index-csv <path>]

The folder_id is the last segment of the Zoho URL:
  https://workdrive.zoho.com/.../folders/<folder_id>

Features:
    * Recursive walk; preserves folder structure locally.
    * Resumable — skips files that already exist with matching size.
    * Access-token auto-refresh (Zoho tokens expire in 1 hour).
    * Optional index CSV pairs `.rup` + `.xls` files in the same
      folder so downstream tools know which pairs go together.
    * Rate-limited to 5 req/s to stay well under Zoho's per-min cap.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


CREDS_PATH = Path.home() / "Procalcs" / "envs" / "zoho-workdrive.json"

# Zoho WorkDrive API base. The datacenter component (`.com`, `.eu`,
# `.in`) is picked from the domain saved during the code exchange.
API_HOST_BY_DC = {
    "accounts.zoho.com":    "https://www.zohoapis.com",
    "accounts.zoho.eu":     "https://www.zohoapis.eu",
    "accounts.zoho.in":     "https://www.zohoapis.in",
    "accounts.zoho.com.au": "https://www.zohoapis.com.au",
}

RATE_LIMIT_QPS = 5.0  # requests per second


# ─── Credential handling ──────────────────────────────────────────────

def load_creds() -> Dict[str, Any]:
    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"Credentials not found at {CREDS_PATH}. Run the code-exchange step first."
        )
    return json.loads(CREDS_PATH.read_text())


def save_creds(creds: Dict[str, Any]) -> None:
    CREDS_PATH.write_text(json.dumps(creds, indent=2))
    os.chmod(CREDS_PATH, 0o600)


def refresh_access_token(creds: Dict[str, Any]) -> str:
    """Trade the refresh token for a fresh access token. Persists the
    new token + expiry back to disk so subsequent runs skip refresh."""
    domain = creds.get("_domain", "accounts.zoho.com")
    resp = requests.post(
        f"https://{domain}/oauth/v2/token",
        data={
            "refresh_token": creds["refresh_token"],
            "client_id":     creds["_client_id"],
            "client_secret": creds["_client_secret"],
            "grant_type":    "refresh_token",
        },
        timeout=30,
    )
    resp.raise_for_status()
    body = resp.json()
    creds["access_token"] = body["access_token"]
    creds["_access_expires_at"] = time.time() + body.get("expires_in", 3600) - 60
    save_creds(creds)
    return creds["access_token"]


def get_access_token(creds: Dict[str, Any]) -> str:
    """Return a live access token, refreshing if necessary."""
    expires_at = creds.get("_access_expires_at", 0)
    if not creds.get("access_token") or time.time() >= expires_at:
        return refresh_access_token(creds)
    return creds["access_token"]


# ─── API wrappers ─────────────────────────────────────────────────────

class ZohoClient:
    def __init__(self, creds: Dict[str, Any]):
        self.creds = creds
        self.domain = creds.get("_domain", "accounts.zoho.com")
        self.api_base = API_HOST_BY_DC.get(self.domain, "https://www.zohoapis.com")
        self._last_call = 0.0

    def _headers(self) -> Dict[str, str]:
        token = get_access_token(self.creds)
        return {
            "Authorization": f"Zoho-oauthtoken {token}",
            "Accept": "application/vnd.api+json",
        }

    def _rate_limit(self) -> None:
        min_gap = 1.0 / RATE_LIMIT_QPS
        now = time.time()
        gap = now - self._last_call
        if gap < min_gap:
            time.sleep(min_gap - gap)
        self._last_call = time.time()

    def list_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """Return every immediate child of a folder — files AND
        subfolders. Handles pagination transparently."""
        items: List[Dict[str, Any]] = []
        page = 1
        page_size = 50
        while True:
            self._rate_limit()
            # workdrive.zoho.com is the same host the download path uses;
            # www.zohoapis.com starts hanging after long sustained walks.
            url = f"https://workdrive.zoho.com/api/v1/files/{folder_id}/files"
            params = {"page[limit]": page_size, "page[offset]": (page - 1) * page_size}
            resp = None
            for attempt in range(5):
                try:
                    resp = requests.get(url, headers=self._headers(),
                                        params=params, timeout=60)
                except requests.exceptions.RequestException as exc:
                    wait = 2 ** attempt * 5
                    print(f"    [list retry {attempt+1}/5] {type(exc).__name__} — "
                          f"waiting {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                if resp.status_code == 401:
                    # Access token expired mid-run; force a refresh and retry.
                    refresh_access_token(self.creds)
                    continue
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = 2 ** attempt * 5
                    print(f"    [list retry {attempt+1}/5] HTTP {resp.status_code} — "
                          f"waiting {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                break
            if resp is None:
                raise RuntimeError(f"listing {folder_id} failed after 5 attempts")
            resp.raise_for_status()
            body = resp.json()
            batch = body.get("data") or []
            items.extend(batch)
            if len(batch) < page_size:
                break
            page += 1
        return items

    def download_file(self, file_id: str, dest: Path,
                       expected_size: Optional[int] = None,
                       download_url: Optional[str] = None) -> bool:
        """Stream a single file to `dest`. Returns True if file was
        downloaded, False if it was already present with matching size.

        `download_url` is the full URL Zoho provides in the file's
        `attributes.download_url` field. It includes org/zid query
        params required for auth on the download-accl host — passing
        it in is more robust than reconstructing the URL locally."""
        if dest.exists() and expected_size is not None:
            if dest.stat().st_size == expected_size:
                return False  # resumable — already have it

        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")

        self._rate_limit()
        # `attributes.download_url` in file metadata points at the
        # download-accl subdomain which rejects OAuth Bearer tokens.
        # The endpoint that DOES accept our token is on the workdrive
        # host under /api/v1/download/. Empirically probed on 2026-07-13.
        # Ignore the metadata field; construct the API URL directly.
        url = f"https://workdrive.zoho.com/api/v1/download/{file_id}"

        def _stream_to(target: Path, response) -> None:
            response.raise_for_status()
            with open(target, "wb") as fp:
                for chunk in response.iter_content(chunk_size=64 * 1024):
                    if chunk:
                        fp.write(chunk)

        last_exc: Optional[Exception] = None
        for attempt in range(5):
            try:
                with requests.get(url, headers=self._headers(), stream=True,
                                    timeout=300, allow_redirects=True) as resp:
                    if resp.status_code == 401:
                        refresh_access_token(self.creds)
                        raise requests.exceptions.RetryError("token refreshed")
                    if resp.status_code == 429 or resp.status_code >= 500:
                        raise requests.exceptions.RetryError(
                            f"HTTP {resp.status_code}")
                    _stream_to(tmp, resp)
                tmp.rename(dest)
                return True
            except requests.exceptions.RequestException as exc:
                last_exc = exc
                tmp.unlink(missing_ok=True)
                wait = 2 ** attempt * 5
                print(f"    [download retry {attempt+1}/5] "
                      f"{type(exc).__name__} — waiting {wait}s", flush=True)
                time.sleep(wait)
        raise RuntimeError(
            f"download {file_id} → {dest.name} failed after 5 attempts"
        ) from last_exc


# ─── Recursive walker ─────────────────────────────────────────────────

def _attr(item: Dict[str, Any], key: str) -> Any:
    return (item.get("attributes") or {}).get(key)


def _is_folder(item: Dict[str, Any]) -> bool:
    # Zoho marks folders with is_folder / type=folder in different revisions.
    if _attr(item, "is_folder") is True:
        return True
    if (item.get("type") or "").lower() == "folder":
        return True
    return False


def walk_and_download(client: ZohoClient, folder_id: str, dest: Path,
                      dry_run: bool = False,
                      index_rows: Optional[List[Dict[str, Any]]] = None,
                      extensions: Optional[List[str]] = None,
                      exclude_re: bool = False,
                      prefix: str = "") -> Dict[str, int]:
    counts = {"files_downloaded": 0, "files_skipped": 0,
               "files_filtered": 0, "folders_visited": 0,
               "bytes_downloaded": 0}

    children = client.list_folder(folder_id)
    counts["folders_visited"] += 1

    files_in_this_folder: List[Dict[str, str]] = []
    for item in children:
        name = _attr(item, "name") or item.get("id")
        item_id = item.get("id")
        if _is_folder(item):
            sub_dest = dest / name
            try:
                sub_counts = walk_and_download(
                    client, item_id, sub_dest,
                    dry_run=dry_run, index_rows=index_rows,
                    extensions=extensions, exclude_re=exclude_re,
                    prefix=f"{prefix}{name}/",
                )
            except Exception as exc:  # noqa: BLE001 — one bad subtree
                # must not abort the whole community walk; log and move on.
                print(f"    !!! subtree failed, skipping: {prefix}{name}/ "
                      f"({type(exc).__name__}: {exc})", flush=True)
                counts["subtrees_failed"] = counts.get("subtrees_failed", 0) + 1
                continue
            for k, v in sub_counts.items():
                counts[k] = counts.get(k, 0) + v
        else:
            # Extension filter — skip files that don't match if the
            # caller supplied a whitelist.
            if extensions is not None:
                ext = os.path.splitext(name)[1].lower()
                if ext not in extensions:
                    counts["files_filtered"] += 1
                    continue

            # RE-exclusion filter — Gerald's convention: prefer non-RE
            # variants of .rup files. When --exclude-re is set, RE
            # variants are dropped entirely at download time (not just
            # at pairing time).
            if exclude_re and name.lower().endswith(".rup"):
                stem = os.path.splitext(name)[0].lower().rstrip()
                # Richard's revision suffix appears as " RE", "-RE",
                # and " -RE" in the archive — match all variants.
                if stem.endswith(" re") or stem.endswith("-re"):
                    counts["files_filtered"] += 1
                    continue

            # Real byte size lives at attributes.storage_info.size_in_bytes
            # (`size` is a human-friendly string like "391.73 MB").
            si = _attr(item, "storage_info")
            size = None
            if isinstance(si, dict):
                size = si.get("size_in_bytes")
            if size is None:
                size = _attr(item, "size_in_bytes") or _attr(item, "size")
            try:
                size = int(size) if size is not None else None
            except (ValueError, TypeError):
                size = None

            local_path = dest / name
            if dry_run:
                marker = "  (dry-run)"
                print(f"{prefix}{name} — {size} bytes{marker}")
                counts["files_skipped"] += 1
                continue

            print(f"{prefix}{name} → {local_path}", end="", flush=True)
            download_url = _attr(item, "download_url")
            downloaded = client.download_file(
                item_id, local_path, size, download_url=download_url,
            )
            if downloaded:
                counts["files_downloaded"] += 1
                actual_size = local_path.stat().st_size
                counts["bytes_downloaded"] += actual_size
                print(f"  [{actual_size} B]")
            else:
                counts["files_skipped"] += 1
                print("  [skipped, already present]")

            if index_rows is not None:
                files_in_this_folder.append({
                    "name": name, "path": str(local_path), "id": item_id or "",
                    "size": size or "",
                })

    # Emit .rup/.xls pairs from this folder into the index.
    # Pairing rule: prefer the non-"RE"-suffix .rup when both variants
    # exist (Gerald's convention — RE = revised/re-export; the base
    # file is the canonical one). Group .rup files by their canonical
    # stem (name minus trailing " RE") and emit one row per group,
    # picking the non-RE variant if present, falling back to the RE
    # if it's the only version.
    if index_rows is not None and files_in_this_folder:
        rup_files = [f for f in files_in_this_folder
                      if f["name"].lower().endswith(".rup")]
        xls_files = [f for f in files_in_this_folder
                      if f["name"].lower().endswith((".xls", ".xlsx"))]

        def _canonical_stem(name: str) -> str:
            stem = os.path.splitext(name)[0].rstrip()
            # Strip trailing " RE" / "-RE" / " -RE" (case-insensitive)
            low = stem.lower()
            if low.endswith(" re") or low.endswith("-re"):
                stem = stem[:-3].rstrip().rstrip("-").rstrip()
            return stem

        def _is_re(name: str) -> bool:
            stem = os.path.splitext(name)[0].lower().rstrip()
            return stem.endswith(" re") or stem.endswith("-re")

        # Group by canonical stem
        by_canonical: Dict[str, List[Dict[str, str]]] = {}
        for r in rup_files:
            by_canonical.setdefault(_canonical_stem(r["name"]), []).append(r)

        for canonical, variants in by_canonical.items():
            # Prefer non-RE
            non_re = [v for v in variants if not _is_re(v["name"])]
            chosen = non_re[0] if non_re else variants[0]
            was_re_fallback = not non_re

            # Best-match .xls: same canonical stem preferred
            canonical_lc = canonical.lower()
            match = next(
                (x for x in xls_files
                    if canonical_lc in x["name"].lower()
                       or x["name"].lower().split(".")[0] in canonical_lc),
                xls_files[0] if xls_files else None,
            )
            index_rows.append({
                "folder": prefix.rstrip("/"),
                "rup_path": chosen["path"],
                "xls_path": match["path"] if match else "",
                "rup_size": chosen["size"], "xls_size": (match["size"] if match else ""),
                "rup_is_re_fallback": "yes" if was_re_fallback else "no",
                "variant_count": len(variants),
            })

    return counts


# ─── CLI ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", required=True,
                         help="Zoho folder_id — last segment of the WorkDrive URL")
    parser.add_argument("--dest", required=True,
                         help="Local destination directory")
    parser.add_argument("--dry-run", action="store_true",
                         help="List files without downloading")
    parser.add_argument("--index-csv", default=None,
                         help="Optional CSV path — writes .rup/.xls pairing index")
    parser.add_argument("--extensions", default=".rup,.xls,.xlsx",
                         help="Comma-separated list of extensions to download "
                              "(default: .rup,.xls,.xlsx). Set to 'all' to "
                              "download every file.")
    parser.add_argument("--exclude-re", action="store_true",
                         help="Drop .rup files whose stem ends in ' RE' "
                              "(Gerald's convention — RE files are revised "
                              "re-exports, non-RE is canonical).")
    args = parser.parse_args()

    extensions: Optional[List[str]]
    if args.extensions.lower() == "all":
        extensions = None
    else:
        extensions = [e.strip().lower() for e in args.extensions.split(",") if e.strip()]
        extensions = [e if e.startswith(".") else f".{e}" for e in extensions]

    creds = load_creds()
    client = ZohoClient(creds)
    dest = Path(args.dest).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    index_rows: Optional[List[Dict[str, Any]]] = [] if args.index_csv else None
    start = time.time()
    print(f"Walking folder {args.folder} → {dest} (dry_run={args.dry_run})")
    counts = walk_and_download(client, args.folder, dest,
                                dry_run=args.dry_run, index_rows=index_rows,
                                extensions=extensions,
                                exclude_re=args.exclude_re)
    elapsed = time.time() - start

    print()
    print(f"Done in {elapsed:.1f}s")
    print(f"  folders visited:   {counts['folders_visited']}")
    print(f"  files downloaded:  {counts['files_downloaded']}")
    print(f"  files skipped:     {counts['files_skipped']}")
    print(f"  files filtered:    {counts['files_filtered']}")
    print(f"  bytes downloaded:  {counts['bytes_downloaded']:,}")

    if index_rows is not None and args.index_csv:
        with open(args.index_csv, "w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["folder", "rup_path", "xls_path",
                                 "rup_size", "xls_size",
                                 "rup_is_re_fallback", "variant_count"],
            )
            writer.writeheader()
            writer.writerows(index_rows)
        re_fallback_count = sum(1 for r in index_rows
                                  if r.get("rup_is_re_fallback") == "yes")
        print(f"  index CSV:         {args.index_csv} "
              f"({len(index_rows)} pairs, {re_fallback_count} RE-fallback)")


if __name__ == "__main__":
    main()
