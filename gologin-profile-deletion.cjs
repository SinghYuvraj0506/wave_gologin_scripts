const fs = require("fs");
const path = require("path");

// get accounts script ---------------
// SELECT
//   a.*,
//   u.email,
//   u.updated_at
// FROM public.accounts a
// JOIN public.users u
//   ON a.user_id = u.id
// WHERE
//   u.updated_at < NOW() - INTERVAL '20 days' AND
//   u.updated_at > NOW() - INTERVAL '30 days'
//   AND u.has_access = false;

// ─── Config ───────────────────────────────────────────────────────────────────
const GOLOGIN_API_TOKEN =
  process.env.GOLOGIN_API_TOKEN ||
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI2ODUzMDNhMGUyNDczOGUyOGVjOWNhZWEiLCJ0eXBlIjoiZGV2Iiwiand0aWQiOiI2ODZiNDg2ODg0YTEzYjdkOTUxNWFkODkifQ.CefiYpRiCocixtheKySboexl-q8lSPe63r45BTN1Y30";
const GOLOGIN_API_BASE = "https://api.gologin.com/browser/v2";

// UUID pattern extracted from names like:
//   instagram-bot-62767c79-0944-40c3-98e4-668df3163b03
const UUID_RE = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;

// ─── Fetch all GoLogin profiles (auto-paginate) ────────────────────────────────

async function fetchAllProfiles() {
  const headers = { Authorization: `Bearer ${GOLOGIN_API_TOKEN}` };
  const profiles = [];
  let page = 0;

  while (true) {
    const url = `${GOLOGIN_API_BASE}?page=${page}`;
    const res = await fetch(url, { headers });

    if (!res.ok)
      throw new Error(`GoLogin API error: ${res.status} ${res.statusText}`);

    const data = await res.json();
    const batch = data.profiles || [];

    for (const p of batch) {
      const match = UUID_RE.exec(p.name || "");
      profiles.push({
        id: p.id,
        name: p.name || "",
        accountId: match ? match[0].toLowerCase() : null,
      });
    }

    console.log(`[fetch] page ${page} → ${batch.length} profiles`);

    if (batch.length === 0) break; // last page
    page++;
  }

  console.log(
    `[fetch] total: ${profiles.length} profiles across ${page} page(s)`,
  );
  return profiles;
}

// ─── Load account IDs from CSV ────────────────────────────────────────────────

function loadAccountIdsFromCsv(csvPath, idColumn = "id") {
  const content = fs.readFileSync(csvPath, "utf-8");
  const lines = content.trim().split("\n");

  // Detect delimiter (comma or semicolon)
  const delimiter = lines[0].includes(";") ? ";" : ",";
  const headers = lines[0]
    .split(delimiter)
    .map((h) => h.trim().replace(/^"|"$/g, ""));

  const colIndex = headers.findIndex(
    (h) => h.toLowerCase() === idColumn.toLowerCase(),
  );
  if (colIndex === -1)
    throw new Error(
      `Column "${idColumn}" not found in CSV. Headers: ${headers.join(", ")}`,
    );

  const ids = new Set();
  for (let i = 1; i < lines.length; i++) {
    const cols = lines[i].split(delimiter);
    const val = (cols[colIndex] || "")
      .trim()
      .replace(/^"|"$/g, "")
      .toLowerCase();
    if (val) ids.add(val);
  }

  console.log(`[csv]   ${ids.size} account IDs loaded from "${csvPath}"`);
  return ids;
}

// ─── Main: find unused profiles ───────────────────────────────────────────────

async function findUnusedProfiles(csvPath, idColumn = "id") {
  const dbAccountIds = loadAccountIdsFromCsv(csvPath, idColumn);
  const allProfiles = await fetchAllProfiles();

  const unused = [];
  const noUuid = [];

  for (const p of allProfiles) {
    if (!p.accountId) {
      noUuid.push(p);
    } else if (dbAccountIds.has(p.accountId)) {
      unused.push(p);
    }
  }
  // for (const p of dbAccountIds) {
  //   if (!p) {
  //     noUuid.push(p);
  //   } else if (!allProfiles.some((ap) => ap.accountId === p)) {
  //     unused.push(p);
  //   }
  // }

  console.log("\n" + "─".repeat(55));
  console.log(`  Total profiles fetched : ${allProfiles.length}`);
  console.log(`  Profiles with no UUID  : ${noUuid.length}`);
  console.log(`  Unused profiles        : ${unused.length}`);
  console.log("─".repeat(55) + "\n");

  // if (unused.length > 0) {
  //   console.log("Unused GoLogin profiles (dry run — nothing deleted):");
  //   for (const p of unused) {
  //     console.log(
  //       `  profile_id=${p.id}  account_id=${p.accountId}  name=${p.name}`,
  //     );
  //   }
  // }

  // Save results to CSV
  const outPath = "unused_profiles.csv";
  const rows = [
    "id,name,accountId",
    ...unused.map((p) => `${p.id},${p.name},${p.accountId}`),
    // ...unused.map((p) => `${p}`),
  ];
  fs.writeFileSync(outPath, rows.join("\n"), "utf-8");
  console.log(`\nResults saved to "${outPath}"`);

  return unused;
}

// ─── Entry point ──────────────────────────────────────────────────────────────

const [, , csvFile = "accounts.csv", idColumn = "id"] = process.argv;

findUnusedProfiles(csvFile, idColumn).catch((err) => {
  console.error("Error:", err.message);
  process.exit(1);
});
