# Request field research

`report.json` contains 24 objects, keyed by the requested C++ class names. Each has endpoint metadata, action group and parameter tokens, C++ types, member offsets, caller provenance, local changes, server mutations, master columns, response readers, reply candidates, confidence, and explicit unresolved points.

Addresses are ELF virtual addresses in the specified arm64 `libgame.so`, before ASLR. `std::string` abbreviates the shipped `std::__ndk1::basic_string<char,...>`. Integer request template arguments `i`, `x`, and `b` mean `int`, signed `long long`, and `bool`. Reply examples describe decoded response groups inside the existing successful transport envelope. Angle-bracket values are placeholders, not literal values to serve.

Binary SHA-256: `a127654037f2f28a70cce7c64ff0a9d291770ea904cdf5bcba59a7af9a6937e4`.

Notable implementation findings:

- Trust coins are **important item `23:300`**, refreshed through `Md0N5abE`. They are not gil or an ordinary bag item.
- `ShopExchangeItemListRequest` inherits the base body and sends no action-specific group. The trust-coin catalog uses `PrizeTranslatorPointMstResponse`; its decoded table is absent from the supplied folder.
- `UnitUsePointRequest` can emit two rows: general bank `woghJa61=0`, then the unit-series bank. General has 14 int64 buckets; series has 13.
- Craft operations are 1 add slots, 2 start, 3 end, 4 cancel. `CraftExeRequest` separately uses group `ayrzi0H4`; execution count is `3EhUu8Xm`, missed by the automated parameter list.
- `UnitSublimationRequest` unlocks a vision-card slot using `20:240000100:1`. Its owned-unit flag is `T9Apq5fS`.
- `MasterCardReleaseRequest` costs 500 lapis and returns the removed item through mailbox mail. Do not credit it directly to the bag or use the friend-gift list.
- Clearing a home display card sends string **`"0"`**.
- Hidden-skill EP is inventory item **`20:1209001000`**. User hidden-skill payload `umTJJ97w` is a comma-separated learned-ID list for the series.
- Vision-card ordinary fusion success is **0**. `Wpro0aE7` is `beforeEXP:beforeLevel_afterEXP:afterLevel`. Keep consumed card objects in the client list during animation: the result scene dereferences them and removes them locally on exit. Persist consumption server-side, but send only a base-card delta in the immediate reply.
- Individual trophy claims are comma-separated trophy master IDs. Gift receiving sends receipt instance IDs; gift sending packs `friendId:giftMasterId` entries.

The remaining gaps are recorded per class. The largest are special crafting policies and packed result details, exact point-to-status formulas, campaign discounts/class-up carryover, and gift send-limit history. No direct constructor callers were found for legacy CraftStart/End/Cancel; that does not prove absence of indirect callers. Missing catalog data and uncertain semantics are marked, not invented.

Verification: parsed the final JSON, checked all 24 requested classes and endpoint records, checked every action token against the binary first-pass token set, and required serializer addresses for every parameter. The project was inspected read-only. No server/client was launched and no live reply was tested, so minimal replies are explicitly static candidates rather than runtime-validated claims.

Cleanup limitation: automatic approval review rejected removal of task intermediates with `blocked by policy`. No existing Trash folder is available inside the authorized current folder. Generated `.asm` files, `symbols.json`, `xrefs.json`, `caller_names.json`, `state_fields.txt`, `research.py`, `digest.py`, `build_report.py`, and their local `__pycache__` remain beside this note. The original `dis.py`, `requests.txt`, and session-owned `codex.log` were preserved.
