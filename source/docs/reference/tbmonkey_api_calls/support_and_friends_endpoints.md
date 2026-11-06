# Support units and friends

A battle's borrowed helper is not in the player's roster. It arrives in its own reply, and the friends
area that feeds it is a separate request. Both share a rule the class names do not suggest: a row has to
be built with **that response class's own field names**. The client reads them directly, and a row built
from a neighbouring class's set crashes the screen instead of failing a parse.

## The two requests

| Request class | request-ID | encode key | URL token | reply |
|---|---|---|---|---|
| `GetReinforcementInfoRequest` | `AJhnI37s` | `87khNMou` | `hXMoLwgE.php` | `ReinforcementResponse` |
| `FriendListRequest` | `u7Id4bMg` | `1iV2oN9r` | `p3hwqW5U.php` | `FriendUnitInfoResponse` |

`GetReinforcementInfoRequest` is fetched on the boot path and refreshed from the home screen. Its rows
are the units a battle can borrow. `FriendListRequest` fills the friends management screen; it is not
the same list, and a battle's helper list works with the friends area empty.

## The support list

`ReinforcementResponse` is bound to **two** tags by the response factory: one carries the list and
leaves it alone, and one empties it. Serve rows on the carrying tag and do not emit the clearing one —
a reply that carries both makes the end state depend on parse order.

An empty list is accepted and is a safe first answer: the home screen renders, and a battle simply has
no helper to offer. Populating the list is what requires care.

### A row has to be built from this class's own field names

A support row carries the friend id, a display name, the unit's level, its rank, equipment, the emblem,
the esper and the vision card. A guest-unit table (`F_GUEST_UNIT_MST`, 185 rows) ships with the client
and already carries many of those values for its own rows, so it is the natural starting source; the
account-specific ids are the server's to author.

The trap is the field names. `ReinforcementResponse` reads its own tokens, and several of them are
shared with the roster's classes while meaning something different — the level in particular. In our
runs a row assembled from the roster's names left the client's row unfilled, and the support-select
layout then dereferenced what it never received: a SIGSEGV inside the layout path, captured live. Built
from this class's own map the fields land; borrowed from a neighbouring class the screen faults. The
level field is the load-bearing one — it is parsed and used in a virtual call before the row is drawn.

Three fields this class reads had no shipped source at the time of our runs: the vision card, the esper
deck and a hidden-skill field. Omit them rather than invent values. An omitted field leaves the client's
default; an invented one can be the wrong shape, which is the failure this subsystem kept producing
until each shape was read from the class's own handler.

### What has been proven

Driven live: the rows render and are selectable, showing the display name, the level, the rank and the
equipment. Rank values have to fall inside the shipped team-level table's range (`F_TEAM_LV_MST`); a
value outside it is not a row the client can resolve. Equipment arrives as party groups joined by `|`,
each group holding `slot-itemId` pairs joined by `@`.

The esper field's shape is recovered and served but was not part of the on-screen acceptance, which
exercised the rank. It is a comma-separated list of nine integers — beast id, rarity, level and six
stats — with the stats derived from the shipped beast tables, described below. A first attempt fed it a
different class's shape and produced a heap over-read, which is the same lesson as the row itself.

One operational detail: the client keeps the list it fetched for the session, so changing the rows
requires a fresh client to see, not just a server restart.

## The vision card on a support row

Two different classes are involved, and it is worth keeping them apart.

**The player's own cards** ride `UserVisionCardInfoResponse`, delivered with the account state. One rule
is hard: a card's level must be at least 1. A level-0 card made the client's growth-rate lookup index
its table at −1, return null and dereference it — a crash captured live. Serving a card that has not
been levelled is not safe.

**The support row's card** is resolved through a second class, `ReinforcementVisionCardInfoResponse`,
whose row list has to be delivered before the support row is drawn. It binds its own two tags (again one
carries and one clears), and its rows are keyed to the support row. One of its string fields keeps only
the text after its first `-`, so it is a pair whose second half has to be the matching row key; a bare
id stores an empty string and resolves nothing. In our runs this class was not served and the card area
stayed empty. The carrier is inferred to be the support reply itself — the reply that already carries
the rows — which is where a run should test it.

## The friends area

`FriendListRequest` reaches `FriendUnitInfoResponse`. Every field that class reads is optional display
data with no verified reader location, so the populated row's shape is not established. In our runs,
sending populated rows faulted the friends scene's own layout; an empty list renders as an empty
friends list and remains the working answer. The support list — the one a battle picks from — is
independent of the friends area and works while the friends list is empty.

## Where the espers ride

The client has **no request** that asks for esper (beast) state. The status replies dispatch by tag
whenever they arrive, so serving them on the ordinary user-info reply is enough: `UserBeastInfoResponse`
and `UserBeastPieceInfoResponse` each bind a full-list tag and an incremental tag, and
`UserBeastDeckInfoResponse` carries the party's deck. All of their tags are in `response_tag_map.json`.

The deck field is a five-slot comma-separated list whose elements are `slot:beastId`, with empty slots
as zero — `0:1,1:0,2:0,3:0,4:0` puts beast 1 in the first slot.

The family's two requests are `BeastBoardPieceOpenRequest` (`0gk3Tfbz`, key `7uxYTm3k`, `Y2Zvnad9.php`)
and `BeastMixRequest` (`C8X1KUpV`, key `WfNSmy98`, `7vHqNPF0.php`). Both are acknowledgements: the
client applies its own change locally, and the server's report of the new state is the next unsolicited
projection, not the reply body. The mix request sends its item cost in the
`20:<itemId>:<count>,...` shape.

Stats are derived rather than served. For each of the six stats the value is
`floor(min + (max − min) × growthPercent / 100)`, where min and max come from the shipped beast status
table keyed by beast and rarity, and the growth percentage from the growth table keyed by the row's
maximum level, growth type and current level. One open point: the shipped rows top out at a partial
growth percentage at their maximum level, so the derivation follows the table rather than a 100%
endpoint.
