// /api/catalog/* — read-only Wrightsoft parts-catalog lookups.
//
// Serves the SQLite extract produced by scripts/catalog-etl/
// mdb_to_sqlite.py from RPRUWSF.mdb (38k+ ActItem rows incl. the
// Rheia pack — present but unpriced, which is exactly the catalog
// gap the BOM module fills). The .sqlite lives outside the repo;
// path comes from CATALOG_SQLITE_PATH.
//
// Uses better-sqlite3 (works on any Node — Cloud Run buildpack's
// runtime predates node:sqlite). If the file is missing the router
// answers 503 rather than crashing the server, so environments
// without the catalog still boot.

import { Router, type Request, type Response } from "express";

const router = Router();

const CATALOG_PATH =
  process.env.CATALOG_SQLITE_PATH ??
  `${process.env.HOME}/Procalcs/Catalogs/catalog.sqlite`;

type SqliteDb = {
  prepare: (sql: string) => {
    all: (...params: unknown[]) => Record<string, unknown>[];
    get: (...params: unknown[]) => Record<string, unknown> | undefined;
  };
};

let db: SqliteDb | null = null;
let dbError: string | null = null;

async function getDb(): Promise<SqliteDb | null> {
  if (db || dbError) return db;
  try {
    const { default: Database } = await import("better-sqlite3");
    db = new Database(CATALOG_PATH, {
      readonly: true, fileMustExist: true,
    }) as unknown as SqliteDb;
  } catch (err) {
    dbError = err instanceof Error ? err.message : String(err);
    console.warn(`[catalog] sqlite unavailable: ${dbError}`);
  }
  return db;
}

function requireDb(res: Response): Promise<SqliteDb | null> {
  return getDb().then((d) => {
    if (!d) {
      res.status(503).json({
        success: false,
        data: null,
        error: `catalog database not available (${dbError ?? CATALOG_PATH})`,
      });
    }
    return d;
  });
}

// GET /api/catalog/sources — manufacturer/supplier registry.
router.get("/sources", async (_req: Request, res: Response) => {
  const d = await requireDb(res);
  if (!d) return;
  const rows = d
    .prepare(
      `SELECT Source AS source, Name AS name, Type AS type, Web AS web
         FROM PartSource ORDER BY Name`,
    )
    .all();
  res.json({ success: true, data: rows, error: null });
});

// GET /api/catalog/parts/search?q=&src=&limit= — description/PN search.
router.get("/parts/search", async (req: Request, res: Response) => {
  const d = await requireDb(res);
  if (!d) return;
  const q = String(req.query.q ?? "").trim();
  const src = String(req.query.src ?? "").trim().toUpperCase();
  const limit = Math.min(Number(req.query.limit) || 50, 200);
  if (!q && !src) {
    res.status(400).json({
      success: false, data: null,
      error: "provide q (search text) and/or src (part source code)",
    });
    return;
  }
  const where: string[] = [];
  const params: unknown[] = [];
  if (q) {
    where.push(`("PN" LIKE ? OR "Description" LIKE ?)`);
    params.push(`%${q}%`, `%${q}%`);
  }
  if (src) {
    where.push(`"PSrc" = ?`);
    params.push(src);
  }
  params.push(limit);
  const rows = d
    .prepare(
      `SELECT PSrc AS source, PN AS part_no, Description AS description,
              Category AS category, Units AS units,
              ListPrice AS list_price, Cost AS cost, Price AS price
         FROM ActItem WHERE ${where.join(" AND ")}
        ORDER BY PSrc, PN LIMIT ?`,
    )
    .all(...params);
  res.json({ success: true, data: rows, error: null });
});

// GET /api/catalog/parts/:src/:pn — exact part lookup.
router.get("/parts/:src/:pn", async (req: Request, res: Response) => {
  const d = await requireDb(res);
  if (!d) return;
  const row = d
    .prepare(
      `SELECT PSrc AS source, PN AS part_no, Description AS description,
              Category AS category, Units AS units, PkgCount AS pkg_count,
              ListPrice AS list_price, Discount AS discount,
              Cost AS cost, Margin AS margin, Price AS price,
              AltPN AS alt_part_no, Status AS status
         FROM ActItem WHERE "PSrc" = ? AND "PN" = ?`,
    )
    .get(String(req.params.src).toUpperCase(), String(req.params.pn));
  if (!row) {
    res.status(404).json({ success: false, data: null, error: "part not found" });
    return;
  }
  res.json({ success: true, data: row, error: null });
});

export default router;
