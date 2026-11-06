# The arena and the Colosseum

Two competitive modes sit past the home screen and share one piece of state that is easy to get wrong:
the orb bar. Both are reached by a door request that is answered with an acknowledgement, and both
build their screens from state the server already delivered rather than from a request made on the
screen itself. That is why a missing or oversized value in either mode surfaces as a crash while the
client is constructing the scene, not as a request that failed.

The arena is the game's Ranked Battle mode; the client's classes for it are `Rb*`, and its screen class
is `RbRankingScene`. The Colosseum's are `Clsm*`. The two share the orb currency, and the arena's
ranking screen is where a server-supplied number can crash the client outright.

## The arena's request family

| Request class | request-ID | encode key | URL token |
|---|---|---|---|
| `RbEntryRequest` | `f8kXGWy0` | `EA5amS29` | `30inL7I6.php` |
| `RbMatchingRequest` | `DgG4Cy0F` | `4GSMn0qb` | `mn5cHaJ0.php` |
| `RbStartRequest` | `eHY7X8Nn` | `P1w8BKLI` | `dR20sWwE.php` |
| `RbEndRequest` | `os4k7C0b` | `MVA3Te2i` | `e8AHNiT7.php` |
| `RbReStartRequest` | `6ZNY3zAm` | `PRzAL3V2` | `DQ49vsGL.php` |
| `RbRankingRequest` | `kcW85SfU` | `SR6PoLM3` | `3fd8y7W1.php` |
| `RbBoardPieceOpenRequest` | `hqzU9Qc5` | `g68FW4k1` | `iXKfI4v1.php` |

Only `RbEntryRequest` has been observed on the wire; the other six are read from the binary's endpoint
table and have not been exercised. The response side has a class per concept — `OpeRbInfoResponse` for
the entry reply, `UserRbInfoResponse`, the matching classes (`RbMatchingListInfoResponse`,
`UserRbMatchingInfoResponse`), the ranking pair (`RbRankingListInfoResponse`,
`RbRankingStateInfoResponse`), `RbResultResponse`, `RbResumeInfoResponse`, the trade-board family
(`RbTradeBoardGroupMstResponse`, `UserRbTradePieceInfoResponse`, `UserRbTradeCompleteInfoResponse`) and
`UserRbVsInfoResponse`. All of their tags are in `response_tag_map.json`.

## What the entry reply has to carry

`RbEntryRequest` is the door. Its reply is an acknowledgement with three fields: a season id, a second,
longer season id, and a flag for the all-orbs rule. Our runs authored all three; the client accepted
them and moved on. Nothing else is requested between that reply and the ranking screen — the screen
does its work from state served earlier.

## The orb bar

Four orb families exist, one per mode: the Colosseum's, the event mode's, the Arms
(equipment-enhancement) mode's and the TFA mode's. Each is a triple — current points, maximum, and a
countdown to the next recovery — and all twelve values ride the team-info reply
(`UserTeamInfoResponse`), which is delivered with the ordinary player state rather than from a
mode-specific endpoint. That is also why an orb problem shows up in the wrong mode's screen: the bar a
screen draws comes from whichever team-info reply the client last received.

The shipped definition table (`F_DEFINE_MST`) supplies the recovery rates. The Colosseum orb carries
both an amount and an interval — 10 and 3,600 seconds; the other three families ship only the interval,
so their recovery amount is an authoring choice. **The caps are not shipped.** No table ties a maximum
to any of the four orbs; the number a server sends is its own. The arena's cap is constrained by the
client's layout (below); the other three are free, and our runs used ten.

Recharging a family is not a mode call: our runs saw the arena's orb-recharge confirm arrive as the
ordinary shop-use request, with the price on the shipped shop row.

### The cap has to fit the client's layout

This is the trap in this mode. The ranking screen builds one orb button per orb up to the cap it was
served, naming them `rb_ranking_btn_orb1`, `...orb2`, and so on. The client's own layout defines **ten**
of them. A cap of fifty therefore asks for an eleventh button, the lookup returns null, and the next
call dereferences it: a SIGSEGV while the scene is being constructed, seconds after the door reply and
with no request in between. The client crashes on a value that looked harmless in the reply.

Keep the cap at or below the number of orb slots the shipped layout provides. With the cap at ten the
screen renders, as our runs showed after the change, and lists no content until ranking rows are
served. One caution for anyone tempted to read a cap out of the data: the one shipped arena row
(`F_RB_DEFINE_MST`) holds the mode's *scoring* parameters, not an orb maximum, so reading a cap from it
is how a mismatched value gets introduced.

## The Colosseum

The Colosseum's door is `ClsmEntryRequest` (`5g0vWZFq`, key `8bmHF3Cz`, `UmLwv56W.php`). The entry
scene's connect check reads nothing from the reply, so any valid response clears it; the class to send
is the next screen's business, not this one's.

That next screen is where the second crash lives. It reads `UserClsmBattleInfoResponse` — battle id,
progress id, round id, round points — and issues no request of its own before doing so. The class has to
ride a reply the client has already received; in our runs it was carried on the entry reply, beside the
progress class `UserClsmInfoResponse`, which names a row of the shipped `F_CLSM_PROGRESS_MST` table.
With no battle-info object built, the scene's first field read dereferences null and the client faults
with a signal rather than a decode error.

**Unresolved, and worth settling before a run:** for an account with no Colosseum battle in progress the
honest values are zeros, and whether zeros are safe here is not established — a zero id can be looked up
in a table with no row zero and yield the same null. Read the scene's layout code around the battle-id
read, or confirm the tables' row-zero convention, before spending a run on a guess.

The Colosseum's other requests — `ClsmStartRequest`, `ClsmEndRequest`, `ClsmLotteryRequest` and the
resume path — are in the endpoint table and have not been driven.

## What is not established

- The arena screens past the entry. The ranking screen renders but lists no activities; matching,
  battles, ranking content and the trade board have not been served or driven.
- Whether zero-valued Colosseum battle info is safe (above).
- The original orb caps. Every cap is authored. Only the Colosseum's ten has evidence behind it, and
  that evidence is the client's layout, not a shipped row.
- The arena's unlock. Reaching the arena requires a story beat, and that unlock is granted through the
  switch mechanism described in `events_and_unlocks_endpoints.md`.
