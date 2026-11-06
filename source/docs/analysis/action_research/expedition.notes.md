# Reverse-engineering notes

report.json contains all 20 requested classes and 69 request parameters, with callers, C++ types, field meanings, reply readers, state changes, confidence and ELF virtual addresses. The project was read only; all outputs were written here.

Evidence is static ARM64 disassembly, relocations/vtables, the response factory, decoded masters and existing server conventions. No live client replay was performed. Reply templates contain $placeholders for canonical state and require the existing success envelope.

Key findings:

- Expedition request Ko86047K is a live quest key. Reply Ko86047K is the master ID; q3D53k94 is the live key. Full quest replies clear first. Status 2 includes finished-unclaimed jobs when endTime<=now.
- Refresh selector 50:1 costs 100 lapis under the supplied exchange definition. Acceleration spends 23:901:N for 3600 seconds each. Start costs 7LIoPpG9 gil plus checked optional consumables.
- Milestone status 2 is claimed. Comeback state 2 is claimable; state 3 draws all-clear. Panel extra keys are L1..L8 and COMPLETED, with exact reward-column mappings in the report.
- MissionUpdate has inherited optional quest fields. ChallengeClear clears locally before sending. MissionSwitchUpdate drains dirty switches and copies carry counts before replying.
- All three party-slot actions serialize the same 13 fields. Request unit token 2A6fYiEC becomes reply 52W9gGbR. Update supplies an equipment event item through Na7YM2v4.
- EX-bonus costs five normal series-piece items per draw. Result grammar is bonusMasterId:obtainedCount comma entries. Update has no proved draw/debit behavior.

Remaining limits:

Original backend roll weights, reset scope, optional map quest rewards and equipment-event slot reconciliation remain unresolved. Mission unlock, dungeon release and milestone definitions are network masters without proved decoded-file replacements. EX-bonus masters have only one row each. Expedition Tr827450 has structured data but a v9 integer reader; display rewards alone cannot establish the loot algorithm. These gaps are explicit per class.

Validation covers the class set, JSON, token uniqueness, evidence coverage and no em-dash characters. No project changes, builds, launches, installs or network requests were made.

Binary SHA-256: a127654037f2f28a70cce7c64ff0a9d291770ea904cdf5bcba59a7af9a6937e4

Cleanup limitation: the tool policy rejected deletion of task-created research intermediates with the reason "blocked by policy". They remain beside these reports in the current codex-re-expedition folder, including branches.json, symbols.json, helper scripts, disassembly text files and __pycache__. No project Trash location was used because this task authorizes writes only in the current folder and no existing Trash is present here. The original dis.py, requests.txt and codex.log were preserved.
