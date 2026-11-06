# Backend reuse architecture

## Scope and current evidence

Target: a personal, sideloaded iPhone game with all gameplay and saves on-device.
A development computer may build/sign the app but must not host its gameplay engine.
This phase adds documentation and desktop verification only.

The Android baseline wraps the original Global 9.0.0 client. The separately inspected
Memorial IPA identifies as Japanese 11.1.0; its main ARM64 executable has cryptid 0,
and it includes FFBEAssets.dylib, Frida Gadget, and ffbe-ios.js. Its main executable
contains __FRIDA_TEXT/__FRIDA_DATA segments consistent with ahead-of-time grafting.
These are static observations, not successful device execution or proof that the
Memorial client retains full battles, summoning, or inventory mutation.

Frida documents ahead-of-time instrumentation for strict code signing:
https://frida.re/docs/gum-graft/
New hook targets must be mapped and prepared for the actual iOS binary. Android
offsets, JNI, C++ symbol names, and object layouts are not portable by assumption.

## Existing communication path

```text
Global Cocos client
  -> original platform calls patched by exvius/android_offline.py
  -> LocalGameConnection / LocalCocosTasks
  -> LocalGameBridge (Java; Chaquopy value conversion)
  -> memorial/android/src/main/python/android_game.py
  -> server/local_game.py: LocalGame.request(method, path, body, headers)
  -> capture_server.Handler via in-memory request/response streams
  -> decrypt, endpoint lookup, response selection, ffbe_pipeline, persistence
  -> encrypted response returned through the same adapters
```

Local resource reads can bypass Python when the file already exists. Native hooks
also provide archive UI, resource materialization, guest login, and client fixes.
The older memorial/local_connection.js Java URL hook is not the release's primary
transport: the current build patches callers and avoids the redundant Java bridge.

## Proposed iOS boundary

```text
Verified iOS client request/resource boundaries
  -> signed Objective-C++/C adapter, preserving callback semantics
  -> one serialized engine worker with embedded CPython
  -> existing LocalGame.request
  -> existing gameplay pipeline and PlayerState
  -> app-private durable saves and installed content
```

Keep the byte-oriented LocalResponse contract: integer status, string header map,
and body bytes. Preserve methods, paths/queries, request bytes, failure handling,
cancellation, and the original callback thread. Acquire Python's GIL on native calls;
do not block the render thread on initialization or slow file operations. Keep large
native assets on disk instead of repeatedly copying them through Python.

If Memorial's messages differ from Global, implement a narrow translation boundary
after measuring the differences. Do not inject Japanese-client conditionals throughout
gameplay code. A direct gameplay API can be considered later if needed; it must reuse
the existing transaction rules rather than duplicate them in Swift.

## Reusable gameplay entry points

| Feature | Existing ownership |
| --- | --- |
| Banners and rates | ffbe_gacha.all_banners/serve_gacha_info; player_state.expand_pool |
| Summon transactions | ffbe_gacha.serve_gacha -> PlayerState.roll_gacha |
| Currency | PlayerState.add_currency/spend_currency/spend_lapis/currency_groups |
| Equipment | exvius_actions.unit_equip |
| Leveling | ffbe_player.serve_unit_mix -> PlayerState.mix_units |
| Awakening/conversion | exvius_actions.unit_class_up/sacrifice |
| Parties | ffbe_player.apply_party_edit |
| Encounters | capture_server dispatch -> battle_content |
| Rewards/clears | ffbe_battle.credit_mission_rewards/grant_cleared_mission |
| Progression | ffbe_player.apply_progress; PlayerState.clear_mission |
| Persistence | ffbe_state.load_state/save_state; PlayerState.load/save |
| New campaign | offline_menu.new_game |

The backend supplies encounters and settles client-reported battle results. It is
not a complete replacement for the original client's combat execution and renderer.
Custom rates can reuse explicit or tier-based pools; future editing must keep displayed
rates, guarantees, costs, and actual rolls consistent.

## Hosting and portability constraints

- Replace Chaquopy with an iOS CPython build and native bridge. Desktop wheels are
  not iOS libraries. Package compatible crypto and YAML dependencies explicitly.
- Use the cryptography backend or a separately verified equivalent. Do not rely
  on the subprocess-based openssl fallback on iOS.
- Bind data paths before importing backend modules. LocalGame supports one active
  data-root/slot binding per interpreter; keep that model initially.
- Provide separate read-only installed content and writable state roots using the
  existing environment overrides. Durable content belongs in application storage,
  not an evictable cache. Preserve saves across content installation and repair.
- Replace Android preferences/version metadata and the sound-resource `/android`
  path assumption in player_state.map_ext_unservable_ignores with platform adapters
  in a future change. No backend refactoring is performed in this phase.
- Retain pipeline ordering and its dependency validation. Mutations precede player
  projection and save operations.
- Surface failed save writes: PlayerState.save currently returns False after logging
  failure. Atomic rename is useful but does not by itself prove power-loss durability.
- Bound request captures on mobile; the current handler writes a record per request.
- Asset/script/table compatibility must be measured per client version. Global and
  Japanese IDs, schemas, platform media, and missing resources may need translation.

## Next milestone and acceptance gates

Summoning will use our own native interface over the existing Python transactions;
do not investigate Memorial's summon interface. The desktop vertical slice is in
`../prototype/` and documented in `summoning.md`. Memorial is not a dependency of it.
Client capability investigation, if needed later, concerns battle and mission paths.

Next embed Python and demonstrate: list banners -> summon -> currency deduction
and unit grant -> save -> terminate -> relaunch -> recover the same state, offline,
using our own native UI. Follow separately with one playable battle. Desktop
smoke success is a prerequisite, not evidence that these iOS gates have passed.

