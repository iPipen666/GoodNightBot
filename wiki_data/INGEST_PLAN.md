# Wiki ingest — architecture & decisions

## Raw downloads (source of truth, DONE)
`wiki_data/raw/data/*.json` — 95 files, all HTTP 200, 0 errors. Counts in `wiki_data/manifest.tsv`.
Field schemas in `wiki_data/schemas.md`. Key files & counts:
- items.json 5944, items_detail.json 5944 ({itemKey:{desc,stats,synthType,dropKey,uniqueMod}})
- stages.json 120, farm_stages.json 108 (expectedGold/EXP, totalHP, goldPerHP…), portal_map.json
- monsters.json 61 (RewardGold/Exp, attacks, attackElements, `stages` list, *_i18n)
- runes.json 197 (+rune_tree.json graph), skills.json 106, passive_skills.json 108
- buffs.json 29, status_effects.json 6, heroes.json 6, grades.json 10
- t/pets.json 8 (+pet_stats 11), t/materials.json 125, t/currencies.json 1
- t/cube_recipes.json 8, t/cube_sub_recipes 31, t/cube_levels 100, recipes.json (synthesis/crafting/cube/extraction)
- t/stat_mods.json 620, t/stat_mod_groups.json 474, mechanics.json (statTypes/modTypes/…), stat_strings.json 117
- boxes/<id>.json — 59 stagebox drop tables. slugmap.json, catalog.json (45 dataset descriptors)

## Reconciliation (our items_db.json vs wiki items.json)
Game files = truth about what EXISTS. items_db.json (5944) and wiki items.json (5944) should
align by item id. Wiki only ENRICHES (stats text, drop sources, effects) — never deletes/overwrites
our records. Our item count must NOT drop. Output: `wiki_data/diff.md`.

## Drop-map (item → where it drops) — the stitch
For each stagebox item B: `boxes/<B>.json.table.entries` = items it yields (type ITEM with
`item.id`, or type ITEMGROUP with `group.id` — expand groups via items.json/catalog if a member
list exists, else record the group as the source). `boxes/<B>.json.stages` = stages where B drops
(`{key,act,no,difficulty,via:monster|box,rate}`). Invert to: `drop_map[itemId] = [{box, boxName,
stages:[{label e.g. "1-1", act,no,difficulty,via,rate,pct}]}]`. Also fold monsters.json `stages`
where relevant. Output: `gamedb/drop_map.json`.

## Target project data layer
- `gamedb/` — shipped normalized JSONs the app loads (copy the relevant raw files, cleaned):
  stages, farm_stages, monsters, runes, rune_tree, skills, passive_skills, buffs, status_effects,
  pets (merge pet_stats), materials (merge t/materials + names from items), currencies,
  cube_recipes, drop_map. Each record keeps its `*_i18n` name dict.
- `gamedb.py` — loader module: load each dataset, accessors, name_in(record, locale) fallback
  (locale→en-US→ru-RU→first), drop sources for an item id. Mirrors db_browser's existing helpers.
- `GAMEDB_SCHEMA.md` — documents every shipped dataset, its record schema, source file, count.

## UI (Wave B) — db_browser.py new tabs
GENERIC data-tab framework (one renderer driven by per-category config: columns, search fields,
detail fields) so all categories are uniform & low-risk — NOT 10 bespoke builders. Priorities:
1. **Stages** tab (act/level/waves/kills, goldPerClear/expPerClear, boss, farm goldPerHP) + click→
   what drops there. 2. **Drop sources in item detail** ("падает из: <box> на стадиях 1-1,1-2…").
   3. Runes, Monsters, Pets, Skills, Status-effects, Currencies, Cube recipes tabs.
Existing Items/Heroes/Grades tabs must keep working. All labels via i18n (en + 16, en fallback).

## Audit (Wave D)
`wiki_data/ingest_report.md`: per section → source N → app N → status (full / explained diff).
0 unexplained discrepancies. Smoke-test every tab + search + language switch.
