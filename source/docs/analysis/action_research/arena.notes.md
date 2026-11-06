`report.json` contains exactly 18 top-level request-class objects. Each includes endpoint identifiers, action groups, parameter types and sources, native addresses, local changes, server obligations, response field schemas, refresh groups, confidence, and explicit unresolved points. Common transport fields are recorded separately from action arguments.

The project was accessed for static research only. All authored work stayed in this folder. Addresses are AArch64 ELF virtual addresses in the supplied `libgame.so`; its SHA-256 is recorded in each object. Evidence comes from native callers, request/response code, relocation-resolved virtual methods, and the specified decoded tables. The first-pass field list was used for orientation, not accepted as semantic proof.

Important implementation findings:

- `RbEntryRequest` and `FriendSuggestRequest` have no action-specific body group. `RbReStartRequest` serializes singleton season ids, ignoring its similarly named request members.
- Arena `bB69ZWQY` is enemy total damage (`long long`). `2q7sZreS` is the result-state hint; ordinary battle construction leaves it at zero. The server must adjudicate the result.
- Arena result screens index four total-point values and two trade-point values without bounds checks. Empty breakdown strings are unsafe.
- Board requests send piece IDs in `mvc31xSV`. Reply `3qJw1vUG` is lowercase hex, indexed by the master `pgS67dFz` column, highest bit first within each nibble. Index 0 alone is `8`; indexes 0 and 1 are `c`. Costs use `mRY52Tib`; rewards use `i9w6ZCFM`.
- Board `N9Aw4kxC` is nonempty board-ID CSV. Its final integer supplies the current board. The getter reads the final element without an empty-list guard.
- Colosseum sends result 1 for defeat, 2 for victory, and normally 0 on Start/Lottery. Start's restart flag is a stored bool serialized with `addParam<int>`.
- Friend detail's omitted first-pass field, `K3BV17gk`, is the profile category. Categories are 1 accepted, 2 outgoing pending, 3 incoming pending, 4 search, 5 suggested. Search requires its dedicated `2K05IxtX` tag and type 4.
- Successful detail callback sets ShowDetails locally. No invented reply token is needed. Accept updates replace the pending row by public friend id; do not also delete that id through `0NVFk2fD`.
- Friend `56gJBnVh` clears accepted rows first; `2vuhy0Ex` updates incrementally. Board piece/completion tags also clear their whole lists.

Reply minima are static candidate templates with prerequisites, not replay-tested payloads. Remaining gaps are marked in the corresponding objects: Arena scoring arithmetic and reward-slot selection, Colosseum lottery/point/drop policies, several packed battle/optional profile subfields, and exact minimum resource-bearing rows for every screen variant. No guessed formula is presented as recovered behavior.
