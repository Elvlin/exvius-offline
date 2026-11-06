# Mode request research

`report.json` contains 29 top-level entries, one per requested class. All addresses are ELF virtual addresses in the supplied arm64 `libgame.so`. Project files were read only. The generic BaseRequest auth/device/version envelope is referenced rather than redefined. Action groups and nested mission payloads are expanded.

Important findings:

- Empty first-pass serializers can be inherited. TowerEntry and TfaResultRewardSelectResume have no action-specific fields. TowerRestart uses MissionReStartRequest at `0x19aaa74`, including `7vh6LXEw`. GloryStart/End delegate to full mission serializers.
- RM sends `jQsE54Iz` operation data and/or `jSC4Tx9H` party snapshots. RmRestart sends operation data only. The shared operation serializer emits restart enum **0**, including on RmRestart. Dispatch by request ID: RM Entry/Retire and Restart/DungeonStart share URLs.
- The `jQsE54Iz` **reply** is a different object: factory `0x1917370` -> `0x191953c` -> constructor `0x197c7f4`, reader `0x197c848`. It reads RNG seed CSV and own-helper strings. It is not UserRmOperationMissionInfoResponse, which has no tag in the supplied map.
- Normal helper `xojJ2w0S` is `UnitInfoBase::getGuestFlg` (`0x1968fb8`). In RM dungeon requests the same token instead means whether the saved guest snapshot string is nonempty.
- Glory's optional key cost is one **item-kind 20, item 106100100**, confirmed by `0x21ca7c0` through `0x21ca7cc` and `F_ITEM_MST.tL6G9egd`. `F_SEASON_EVENT_GLORY_MST.1b4t0SRA` is an exchange-shop gacha ID, not this item.
- Fresh mission cost comes from `F_MISSION_MST.CQN15Hgr/B6kyCQ9M`, with rank/half-cost rules at `0x1a78c48`. Shipped Survival missions have zero base cost. Restart is not evidence for a lapis continue charge.
- Retire's switch CSV uses `UserSwitchInfo::getAlwaysSendSwitchHistCsv` (`0x1d8b108`), selecting switch types 104/204. Successful-end switch CSV uses the broader client-managed filter (`0x1d8acb8`).
- Survival party state is `2w9Iyeaq.3KJpzuC5`, packed as `1@summonGauge@position|hp|mp|lb|badStates|limitBulletCsv|skillIntervalCsv|braveShiftCsv|buffCsv...`. Positions are live battle slots. Empty-party state is `1@0`.
- TFA reward fixing sends reward tuples plus an optional replaced slot, not a choice index. Resume needs candidate data in `GachaExeResponse.UJz5QED2` as well as obtained slots. The two bonus-preview multipliers are party unit bonus and gambit drop bonus, scaled by 1,000 and rounded before string serialization (`0x249a3dc`, `0x249a3e8`, `0x1997174`, `0x19971b4`).
- Quest start/completion pairs use `1sGiqV9T.i9han5Sz` and `1sGiqV9T.9YPZuB2i`, respectively. Both values are `questId:questSubId`.

Limits: reply requirements are static downstream-consumer inferences, not captured endpoint responses or live screen tests. Every minimal reply is labeled accordingly. Unknown response field meanings, some packed-history subdivisions, server scoring, refund rules and reward banking boundaries remain explicit. No missing event/reward master or original server settlement policy was fabricated. Use authoritative state plus a per-run settlement ledger when implementing; PlayerState.groups() alone does not supply mode-specific state.
