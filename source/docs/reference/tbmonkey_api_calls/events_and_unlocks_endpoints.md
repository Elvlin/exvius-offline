# Events, emblems and the switches that open them

A limited event is not unlocked by data shipped beside it. The server decides which events the client
can see, feeds one gate list, and grants the story switches that open feature tiles. It covers the
three surfaces this involves: the event gate, the emblem screens and the crest campaign, and the
function switches behind the home screen's locked tiles.

## The gate list an event area reaches the client through

An event area appears when a reply carries a row for it in `SpDungeonCondMstResponse` (tag
`0xkoNP8U`). The list is **replace-on-read**: a reply that carries it replaces the client's list, so the
row has to ride one of the replies that already serve the list rather than being appended to an
unrelated one.

A row names the area, its dungeon and its first mission. Those three can be **derived** — the dungeon
and first mission come out of the shipped mission tables — while the window, the tab and the art are
authored, because no shipped table dates a live event or assigns its tab.

The tab is decided by the row's event-type field, and the tab index is one less than that value:
type 1 is the event tab, 2 is training, 3 is the enemy tab, 4 is special and 5 is the ordeal tab. A
missing row does not hide the area from one tab; it hides it from all five.

The gate list's proven consumers are the vortex's tabs and the survival events. Whether a *story* event
is listed from the same list is not established — it has been wired but not driven, and a run is the
oracle.

## The event's content is downloaded, not answered

The tile's art and the event's maps are per-location packs, fetched on demand by names the client builds
out of its own resource tables. The mechanism is the same as a town or a field: the boot reply configures
the host, and the pack has to exist at the path the client asks for, or the location fails. In our runs
an event tile with no served area pack drew its frame and nothing else. `towns_and_maps_endpoints.md`
has the URL shape and the download/ignore gate; `missing_cdn_packs.md` lists the event-layer packs that
no build we can compare against contains.

## Event battles are often already derivable

An event's battles come from the same mission-resource reply as any mission
(`DungeonResourceLoadMstListRequest`, described in `validated_endpoints.md`). The question is whether the
content behind a mission has to be authored.

It often does not. Of the 913 event areas with at least three missions, **707 are fully
battle-derivable** from the client-side JP corpus: every mission id has a phase ladder and encounter
groups, so a server can assemble the battle without authoring anything. The remaining areas — the Global
story arcs above all — are where the composition was never shipped and has to be authored.

The same JP/Global gap appears in the event's drop items: the JP corpus's drop ids are not the Global
item ids, so mapping an event currency onto a shipped item is an authoring choice and should be labelled
as one.

## The emblem screens

The crest beside the player's name comes from a small family of requests:

| Request class | request-ID | encode key | URL token | reply |
|---|---|---|---|---|
| `PlayerEmblemEntryRequest` | `Z7J9H6TK` | `F7A2MJoE` | `huKNdci6.php` | `UserPlayerEmblemInfoResponse` |
| `PlayerEmblemSettingRequest` | `19YwqU2T` | `76kGLIgN` | `cswGxj8F.php` | `UserPlayerEmblemInfoResponse` |
| `sgEmblemEventRequest` | `wMWvnYDR` | `U9QMZrFq` | `wMWvnYDR.php` | the three campaign classes below |

`PlayerEmblemEntryRequest` is the select screen's "which emblems do I own?" call. It has no fields of
its own beyond the common envelope, and its reply carries the owned-emblem list. The list may be empty,
but the reply has to carry a dispatchable group: zero bytes sends the client into its connection-error
retry loop.

`PlayerEmblemSettingRequest` displays one. It sends the user id and the emblem id, and is answered with
the same owned list. The crest actually drawn beside the name is delivered separately, on the team-info
reply; the id 0 is the legitimate "no emblem" value.

The emblem catalogue is a shipped master-data table (`F_EMBLEM_ITEM_MST`, 522 rows), downloaded through
the ordinary MST path. **Ownership has no shipped grant.** No table records which emblems an account has
earned — the game's own source is the trophy list — so a server that wants a crest to show has to grant
ownership itself.

One wire habit worth knowing: the setting request's group name is also the tag its reply is dispatched
by, so it is one token in both directions. Build the reply from the server's own state rather than
echoing the request back.

## The emblem event (the crest campaign)

The screen the crest opens — distinct from the select screen above — sends exactly one request,
`sgEmblemEventRequest`. Its body is the common envelope with no group of its own, so the reply's tags
are the server's choice. Three reply classes carry the campaign, and one body can announce all three:

| Tag | Response class | What one row carries |
|---|---|---|
| `VY9DTFhP` | `sgUserEmblemMonthlyInfoResponse` | campaign id, current crest count, pass status, window |
| `VVzhCSFB` | `sgUserEmblemWeeklyInfoResponse` | one row per objective: id, progress, cleared flag |
| `ru7MthFL` | `sgEmblemMilestoneInfoResponse` | one row per milestone: id and window |

The two date fields are `%Y-%m-%d %H:%M:%S` strings, not epochs — the client converts them on read, the
same way the panel-quest schedule does.

The campaign data ships. `F_EMBLEM_WEEKLY_MST` holds the objectives (a type: point target or mission
clear; the target mission for clear types; a count; the reward), and `F_EMBLEM_MONTHLY_MST` holds the
tiers (the crest count at which a tier pays, with separate free and passholder reward specs). What does
not ship is the live campaign's window and the pass ownership, so both are authored.

The credit rule follows from the tables: one crest per cleared objective, and the crest is an important
item carried in the client's type-23 bag. A mission-clear objective is credited when its mission is
completed — the mission-end body names the mission and the area. Point-shaped objectives accumulate in
an event the server would have to model on its own. Tier rewards are delivered by mail, with a numeric
mail id so a receipt can match it; the zero-crest row is the campaign's opening gift.

**What is not established:** whether this screen actually consumes those three groups on this reply.
The scene's connect handler read nothing when we read it, and the reply is the campaign's only request,
so serving them here is an inference with a run as its test. Pass ownership has no shipped source
either.

## The switches that open feature tiles

Several tiles are gated by the function table (`F_FUNCTION_MST`): each row pairs a function with a
switch id, which decodes to a switch type and an index. Three examples, all granted the same way: the
vortex (switch ids `10004001` and `10005001` — type 100, indices 6 and 8), the espers (`10007400` —
type 101, index 14) and the equipment-enhancement tile (`10004002` — type 100, index 7).

No shipped table grants any of those bits. They are the server's to set, which is the intended shape:
they encode story progress, and no shipped row carries it. One rule matters when you set them: switch
state is carried per type, and a reply carrying a type **replaces** that type's state rather than
merging into it, so each reply has to carry the whole state you want the client to hold.

The client also acquires some type-100 flags itself while playing and reports them, so the requests
around a story beat are where a server can observe which beat was reached. Type 100 is the main-story
family; type 101 is the esper family. The arena's own unlock is recorded in this family too.
