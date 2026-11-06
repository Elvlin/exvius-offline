# Summoning vertical slice

## Interface and ownership

The temporary frontend is a terminal menu, not a web server. It calls the Python
facade directly. Nothing connects to or repackages the Memorial client.

```text
summon_cli.py (terminal commands or JSON output)
  -> SummonService.banners / details / state / summon
  -> ffbe_gacha catalogue + unit_name + player_state.expand_pool
  -> PlayerState.roll_gacha (unchanged transaction implementation)
  -> PlayerState.save / load (existing persistent campaign format)
```

`ffbe_gacha.serve_gacha` is the original Global encrypted-response adapter. It parses
Global request fields, resolves the selected offer, invokes roll_gacha (or the box
handler), scores related quest/archive actions, and formats the response. A new UI
does not need Global wire encryption or animation responses. This slice calls the
underlying roll_gacha operation directly; it does not claim to reproduce every
quest/achievement side effect of serve_gacha. Those orchestration effects need
explicit coverage when integrating progression later.

The facade owns validation of exposed operations, serialization, error translation,
and saving. It never chooses a random unit, calculates prices, writes rates, grants
units itself, or modifies banner definitions. The legacy backend owns pool expansion,
weighted selection, guarantees, cost deductions, grants, and summon counters.

| Operation | Returned data |
| --- | --- |
| banners() | Banner identifiers/names, primary prices/draws, offers, support flags |
| details(id, offer) | Existing price/draw count, guarantee definition, expanded base pool with weights and names |
| state() | Currency balances, owned unit instances, last pull, metadata-mode flag |
| summon(id, offer) | Persisted result awards with names plus updated state |

All return plain JSON-compatible values. A native Objective-C++ bridge can expose
the same operations without a listener. Use one data root per interpreter and one
service/writer per campaign. Methods serialize on a reentrant lock; returned data
does not expose mutable player state to the UI. Cross-process concurrent writers
and HTTP retry/idempotency protocols are outside this terminal-only slice.

Primary and secondary are offer identifiers, not arbitrary repeat multipliers.
The real backend charges the offer once (500 lapis for a single, 5000 for eleven
on the demo banners). Ticket, box, step-up, selection, and mixed-reward interfaces
are deliberately not exposed yet. Existing backend implementations remain intact.
Catalogue entries outside this supported subset can be listed but cannot be pulled.

Errors have codes: unknown_banner, invalid_offer, unsupported_banner,
summon_refused, save_failed. The backend returns None for several refusal causes;
the interface does not incorrectly label all of them as insufficient currency.
On refusal, exception, or failed save, the facade restores its pre-operation state.
Successful responses are returned only after PlayerState.save reports success.
This is not an additional guarantee of filesystem power-loss durability.

## Missing preserved data and the explicit demo

The checkout lacks decoded master tables. `--demo` materializes minimal metadata in
the ignored workspace. It selects unchanged authored banners 9100203 and 49 from
server/gacha_authored.json, including their fully enumerated tier pools, prices,
featured shares, and secondary guaranteed slots. It does not invent a smaller pool.

The fixture generator walks these definitions to provide unit IDs/rarities required
by the existing grant logic, placeholder names (`Fixture unit ID`), and starter
equipment identities. Other referenced tables are empty. These are authored test
records, not copied original tables. There are no artwork, real stats, combat data,
movies, or executable inputs. The banners themselves are read from the repository,
not copied into a second editable catalogue. Unit IDs remain visible in the UI.

This proves real summon transactions against full explicit banner pools and published
weights. It does not prove complete Global master-data compatibility or playable
units in a game client. Demo campaigns must not be imported into the eventual game.
Base pool probabilities are labelled separately from guarantee rules; they are not
claimed to be the final probability for every guaranteed slot.

`--data PATH` instead loads preserved tables and ffbe_gacha.all_banners(). Keep those
files outside Git. Use a separate prototype save, never an existing Android campaign.
No missing preserved-data input is silently replaced with demo data.

## Running from repository root

Install the Phase 1 dependencies if necessary, then launch:

```powershell
source/ios/.venv/Scripts/python.exe -B source/ios/prototype/summon_cli.py --demo
```

In the menu:

```text
banners
details 9100203
summon 9100203
summon 49 secondary
state
quit
```

Demo mode seeds 10000 free lapis only when creating a new campaign. Reopening never
refills balances. To start a separate experiment use a new `--workspace` directory.
Data and saves default to source/ios/.local/summon-demo (ignored).

JSON commands are useful for bridge development and scripted validation:

```powershell
source/ios/.venv/Scripts/python.exe -B source/ios/prototype/summon_cli.py --demo --json banners
source/ios/.venv/Scripts/python.exe -B source/ios/prototype/summon_cli.py --demo --json summon --banner 9100203
source/ios/.venv/Scripts/python.exe -B source/ios/prototype/summon_cli.py --demo --json state
```

Each command is a separate process loading the same save. JSON goes to stdout;
backend diagnostics go to stderr. Failed commands exit 1. With preserved data:

```powershell
source/ios/.venv/Scripts/python.exe -B source/ios/prototype/summon_cli.py --data D:/personal/ffbe-data --save source/ios/.local/preserved-summons.json --initial-lapis 10000
```

The optional development credit applies only to a new campaign; default preserved
mode credit is zero. Do not point --save at a real game save. macOS/Linux use the
virtual environment's bin/python instead of Scripts/python.exe.

## Automated validation

```powershell
source/ios/.venv/Scripts/python.exe -B source/ios/tests/test_summon_service.py
source/ios/.venv/Scripts/python.exe -B source/ios/tests/smoke_backend.py
```

Seven summon tests cover single charge/grant, eleven-pull charge/guarantee/unique
instances, insufficient-currency rollback, exact original banner and tier weights,
fresh-process save reload (including counters and no startup refill), failed-save
rollback, and invalid identifiers/offers. Only disk-save failure is mocked; RNG,
banner expansion, currency operations, and unit granting run the actual backend.
Temporary test campaigns stay under ignored .local and are cleaned on exit.

## Next native milestone

Embed CPython in a minimal SwiftUI/Objective-C++ host and call this facade using
JSON-compatible values on a serialized worker with correct GIL ownership. Display
the two banners, current balance, and awarded IDs/names, then prove force-close
and cold-launch persistence on the iPhone. This requires no Memorial summon UI.
Use real preserved metadata before claiming playable unit compatibility. Battle
frontend integration is a separate later milestone.
