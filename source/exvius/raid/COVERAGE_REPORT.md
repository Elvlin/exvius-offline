# Verified source coverage and model results

## Data audit (not runtime execution)

The pinned ZIP matched SHA-256 cb91b0cfea59f22285fa7c707d10adff5dd2561b014da66cb0c6af87c2eb489e. Each TSV header row count was checked against the actual streamed rows:

| Table | Verified rows |
|---|---:|
| Mission | 22,603 |
| Mission phase | 39,993 |
| Battle lottery | 30,076 |
| Battle group slots | 59,441 |
| Monster | 16,937 |
| Monster parts | 17,147 |
| Monster skill set | 5,305 |
| Monster skill | 17,926 |

These are indexed rows, not numbers of playable events or uniquely classified bosses. Counts do not establish whole-game coverage.

Selected mission 8960101 has one mission row, phase, positive lottery candidate, group slot, monster, part and skill set; its skill set resolves to 25 skill definitions. All selected chain references and its community break entry are present. The complete selected raw rows, original provenance headers, TSV hashes and community source citation are preserved in source_audit.json. No archived repository module was imported or executed.

## Mechanic coverage distinctions

- Available data: actual selected mission, lottery/group, monster/parts and 25 skill rows.
- Community-derived data: Bahamut part 407031103 break gauge starts at 10,000 BP, then 30,000 BP after first break; duration 3 turns. Broken-form stats and weapon-specific BP values are preserved as evidence, not simulated.
- Missing/unverified for this deliverable: actual raid event classification and original global HP, rank and reward policies. Other saved source archives are not claimed absent; this pass audits only the pinned server ZIP.
- Unsupported simulation: action selection/AI, skill effect decoding, incoming damage/party deaths, phase transitions, damage formula, elemental/weapon resistances, chain/killer/buff calculations and random branches.
- Explicit approximation: break starts after the supplied triggering turn and lasts the following full turns; no BP damage during break. This timing requires client verification.
- Untested combat: client boot, compatibility, encounter traversal, fight correctness, local raid persistence and rewards.

## Reproducible authored model checks

Seven unit tests passed: lethal HP/overkill cap, incomplete trace, additive break re-arm without accumulation, lethal turn suppressing new break, no silent trace repeat, invalid integer rejection, and authored solo-target multiplication.

The example uses a deliberately synthetic 100-HP target and authored final-damage/BP trace with the source-backed break gauge parameters. It clears in six modeled turns and triggers two modeled breaks. This checks arithmetic only; it is NOT a Bahamut victory or evidence of balanced raids.

Measured audit + tests + CLI: 0.845 seconds wall time, peak child RSS 13,056 KiB, all three subprocesses exited 0. A 128 MiB virtual-memory limit and 90-second bounded execution were used. Detailed output is in execution_metrics.json, test_results.txt and example_result.json.

The useful next step is a verified real raid identifier and measured compatible-client damage/BP traces. The current functions immediately support trace comparisons and authored local-HP workload targets without pretending to reproduce full combat. No live server hook or save mutation is included.
