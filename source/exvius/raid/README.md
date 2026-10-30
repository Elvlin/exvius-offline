# Offline encounter coverage and solo-raid workload model

This is an additive developer tool, not an integrated combat engine or playable raid. It never imports, runs, or installs downloaded repository code. It cannot establish a combat pass or client acceptance.

## What is real

Pinned source: TBMonkey/ffbe-gl-server commit 7707880725637ece42dbc42820c29db424f6f4cc. The existing base ZIP SHA-256 is checked before data is read. Eight compact battle TSV tables are available in that ZIP, even though the integration's trimmed vendor tree lacks the table directory. `audit_source.py` streams their contents, checks row counts and records TSV hashes plus original source headers. Header hashes describe upstream NDJSON, not the TSV itself, and are not independently reverified here.

The selected encounter is mission 8960101, referenced as Heavenly Flames PRO in the upstream community break file. It is an encounter fixture, NOT asserted to be a raid. The audit preserves all positive-weight lottery alternatives, every enemy slot and multipart row, and exact referenced skill rows. Raw stat/AI tokens remain raw; field presence does not prove semantics or faithful AI implementation.

Source paths:
- server/content/battle/F_MISSION_MST.tsv: mission qo3PECw6 → area U9iHsau3.
- F_MISSION_PHASE_MST.tsv: mission qo3PECw6, phase 6v7y3QcJ, type gou39JeI=2, lottery 6uIYE15X.
- F_BATTLE_LOTTERY_MST.tsv: pool c2gnh6Jd, positive weight ixDq7yJ8, group 2fY1IomW.
- F_BATTLE_GROUP_MST.tsv: group 2fY1IomW → monster xqartN26; preserve slot multiplicity.
- F_MONSTER_MST.tsv and F_MONSTER_PARTS_MST.tsv: xqartN26; parts distinguished by 6Yc4RkdM.
- F_MONSTER_SKILL_SET_MST.tsv: A5x02C6a → comma-separated 7qxLC5hP.
- F_MONSTER_SKILL_MST.tsv: skill 6E5u1xrs. Preserved, not interpreted.
- server/battle_content.py: chain and break semantics documentation; source read, not executed.
- harness/break_status_community.json: community-derived break gauge, duration and broken-form data, not recovered first-party wire tables. Each selected entry has source gist links. Its cited claims are not independently corroborated in this task.

## Usable model

`simulate(config)` and `python3 raid_model.py example_workload.json` replay explicitly supplied final per-turn damage and final BP damage. HP is user-supplied; the example's 100 HP is an unmistakably synthetic test dummy, not invented boss data. No ATK/DEF, resistance, killers, chain, variance, buffs, AI, party survival or skill damage is calculated. Feed measured client traces when available; use separate traces for different strategies.

The break gauge uses the documented base-plus-delta-after-first-break rule. Repeated breaks re-arm at base + delta, not an accumulating delta. Timing is an explicit approximation: a break triggered at the end of a turn lasts the following N full turns; BP damage during break is ignored. Client ordering, preemptives, interrupts, simultaneous lethal damage and phases need verification. Submitted damage is already final and receives no automatic broken-form multiplier.

`solo_target(damage_per_attempt, desired_attempts)` recommends an authored local HP pool by multiplication. It is NOT an original FFBE raid formula or automatic in-game patch. It deliberately avoids global population/rank services. Rewards and pool persistence belong to separately tested integration work.

## Reproduce

Run from this directory using Python 3.11 or newer:

    python3 audit_source.py /path/to/base.zip --mission 8960101 --output source_audit.json
    python3 -m unittest -v test_raid_model.py
    python3 raid_model.py example_workload.json

Input is documented in scenario.schema.json. Model validation rejects negative, Boolean and noninteger quantities, but is not a full JSON Schema validator. Source audit missing-reference arrays must be reviewed; clean links do NOT mean all original content was recovered. Inventory counts cover this ZIP only, not the other saved source archives.

## Runtime verification still needed

1. Identify an actual raid mission using independently sourced event metadata, and verify all battle candidates, stat mappings, AI and skill semantics for its version.
2. Load its compatible original client/assets under separately authorized execution; prove entry, fight, victory, failure and restart.
3. Record per-turn final damage/BP, actual break entry/end ordering, boss phases, party deaths and relevant random branches. Compare traces against the model, documenting unsupported mechanics rather than silently approximating them.
4. Calibrate solo HP target to measured weak/middle/strong parties and desired attempts. Measure reward/time, stamina/orb assumptions and repeated completion. Do not claim a balance result from one synthetic trace.
5. Integration must remove live global-HP/rank dependencies and implement transactional reward/local-progress saves, then test replays and crashes. This module changes no server responses or save data.
