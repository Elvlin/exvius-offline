# The validated request paths

Two notes already map this client's server-facing surface. `FFBE_SERVER_CONTRACT.md` lists every
endpoint path compiled into the binary, and `boot_to_home_endpoints.md` follows the fifteen of them
that carry the client from launch to a playable home screen.

This note is the next step. It lists the requests a client sends once the home screen is up and the
game is actually being played — a mission, a summon, the recurring home polls — in the order the
client sends them, and says what each reply has to carry. Everything here was driven against a local
server — the client sent the request in a captured run and accepted the answer — except where a
section says an effect is still unproven.

It deliberately stops short of the field level. A response body is a JSON object whose keys are
eight-character tokens, and those token maps are the part left to you. Recovering one is mechanical —
the method is at the end of `FFBE_SERVER_CONTRACT.md` — and it is the reason this note names the
requests and the shape of each answer without handing over the answer itself.

## The requests this note covers

| Area | Request class | request-ID | encode key | URL token | reply |
|---|---|---|---|---|---|
| mission | `MissionWaveStartRequest` · `TfaMissionStartRequest` | `BSq28mwY` | `d2mqJ6pT` | `Mn15zmDZ.php` | `ScenarioBattleInfoResponse` |
| mission | `DungeonResourceLoadMstListRequest` | `jnw49dUq` | `3PVu6ReZ` | `Sl8UgmP4.php` | `DungeonResourceLoadMstResponse` |
| mission | `MissionEndRequest` | `x5Unqg2d` | `1tg0Lsqj` | `0ydjM5sU.php` | `MissionResultResponse` |
| summon | `GachaEntryRequest` | `rj6dxU9w` | `39cFjtId` | `tUJxSQz7.php` | the banner group set |
| summon | `GachaInfoRequest` | `UNP1GR5n` | `VA8QR57X` | `3nhWq25K.php` | the banner group set |
| summon | `GachaExeRequest` | `9fVIioy1` | `oaEJ9y1Z` | `oC30VTFp.php` | `GachaExeResponse` |
| home | `RoutineHomeUpdateRequest` | `Daud71Hn` | `aw0syG7H` | `1YWTzU9h.php` | `RoutineHomeUpdateRespose` |
| home | `RoutineEventUpdateRequest` | `4kA1Ne05` | `V0TGwId5` | `WCK5tvr0.php` | `RoutineEventUpdateRespose` |
| home | `RoutineWorldUpdateRequest` | `6H1R9WID` | `XDIL4E7j` | `oR1psQ5B.php` | `RoutineWorldUpdateRespose` |
| news | `NoticeUpdateRequest` | `CQ4jTm2F` | `9t68YyjT` | `TqtzK84R.php` | `NoticeMstResponse` |
| friends | `FriendListRequest` | `u7Id4bMg` | `1iV2oN9r` | `p3hwqW5U.php` | `FriendUnitInfoResponse` |
| party | `PartyDeckEditRequest` | `TS5Dx9aZ` | `34qFNPf7` | `6xkK4eDG.php` | `UserInfoResponse` |
| party | `UnitEquipRequest` | `pB3st6Tg` | `45VZgFYv` | `nIk9z5pT.php` | `UserInfoResponse` |
| shop | `PurchaseSettingRequest` | `QkwU4aD9` | `ePFcMX53` | `9hUtW0F8.php` | `UserPurchaseInfoResponse` |
| shop | `PurchaseListRequest` | `BT28S96F` | `X3Csghu0` | `YqZ6Qc1z.php` | `UserPurchaseListInfoResponse` |
| mail | `MailListRequest` | `KQHpi0D7` | `7kgsrGQ1` | `u3E8hpad.php` | `UserMailInfoResponse` |
| arena | `RbEntryRequest` | `f8kXGWy0` | `EA5amS29` | `30inL7I6.php` | `OpeRbInfoResponse` |
| Colosseum | `ClsmEntryRequest` | `5g0vWZFq` | `8bmHF3Cz` | `UmLwv56W.php` | `UserClsmInfoResponse` |
| emblem | `PlayerEmblemEntryRequest` | `Z7J9H6TK` | `F7A2MJoE` | `huKNdci6.php` | `UserPlayerEmblemInfoResponse` |
| emblem | `PlayerEmblemSettingRequest` | `19YwqU2T` | `76kGLIgN` | `cswGxj8F.php` | `UserPlayerEmblemInfoResponse` |
| emblem | `sgEmblemEventRequest` | `wMWvnYDR` | `U9QMZrFq` | `wMWvnYDR.php` | the three campaign classes (see the events note) |

The request-ID, encode key and URL token are the three values recovered from each class's own
accessors, and they match the contract's appendix. The reply column names the response class whose
tag the client expects; `response_tag_map.json` is the full tag-to-class table. The two summon
entry replies use the banner group set — `GachaMstResponse`, `GachaDetailMstResponse`,
`GachaScheduleMstResponse`, `UserGachaInfoResponse` and `UserGachaStepInfoResponse` — linked by
shared banner ids.

## Missions and battle

The client admits a mission, fights it, and reports the end in three requests. The one in the middle
is the surprising one.

It sends the mission-start token first. That token is shared by `TfaMissionStartRequest`,
`MissionWaveStartRequest` and `GrandMissionEntryRequest`, and the three are identical on the wire, so
one reply serves all three. The reply itself is almost incidental: an empty scenario-battle group is accepted, because the
scene routing is internal.

Then it sends `DungeonResourceLoadMstListRequest`, which does not sound like battle traffic at all.
This is where the battle's content lives. The reply carries the mission's phase ladder — each phase a
number, a type (battle or story), and, for a battle, the encounter group to spawn — followed by the
encounter groups, the monsters, their parts and their battle stats. Put the content in the
mission-start reply instead and the client ignores it; that mistake produces a mission that starts
and immediately ends.

Two rules about that content are worth knowing before authoring it. Phase numbers are matched against
a counter that begins at one, so the ladder has to be contiguous from 1 — a gap makes the client treat
the mission as over. And the failure mode for an empty or all-skipped formation is not an error: it is
the same immediate end, which is easy to mistake for a scene-routing problem.

### What that content has to carry

The groups this reply hands over are not just stats. Four things in them are load-bearing, and each one
fails quietly or loudly in its own way.

**A monster's parts are several rows.** One monster's body and limbs are separate rows that share the
monster id and differ in a parts number — 1 is the body, 2 and up are the limbs. The client builds one
battle unit per row, so serving only the first row gives a multi-limb enemy a single limb. Read every
row that shares the id.

**Every skill a part names has to be in the reply.** A part carries a skill set, and the client resolves
each id in it against the monster-skill rows in the same reply. A missing row is not an error: the client
skips that skill. A monster whose whole list is missing degrades to a plain attack, which looks like an
AI problem and is not one.

**The break groups are mandatory as soon as a part names a break id.** A part with a non-zero break id
makes the client look up two further groups — the broken form's stats and the break gauge. It null-checks
neither, so a part that names a break id while those groups are absent faults at battle load. Send both,
or name break id 0 and the client skips the path entirely. Inside the gauge group, one field is a fixed
**sixteen-entry** comma-delimited list of per-weapon values, read on every attack: it is not optional
either, and an empty one faults on the first hit. The same group's fields set the gauge pool again after
the first break, which is how a fight can have a larger pool the second time.

**The behaviour is not yours to send.** An enemy's turn-by-turn script ships inside the client as its own
table; the parts row carries the id that selects it. The server supplies that id and the skills the
script indexes, nothing more — so "the boss did nothing" is either a scripted turn or a skill list that
falls short of what the script asks for.

The last request is `MissionEndRequest`, and its reply is the result screen. That response class binds
to the client's own result object and clears it before reading, so gil, experience, drops and reward
rows exist only if the reply carries them. An empty reply is an empty result screen. The mission's
clear flag is granted in the same reply as a switch group; the client does not ask for it separately,
and switch containers are replaced per type rather than merged, so every reply that carries switches
has to carry the whole state you want the client to hold.

One behaviour here is a design decision rather than a rule. A phase's drop list is a candidate pool,
and the client displays whatever it is handed without using the supplied rate. Serving the pool
verbatim therefore shows every candidate at once. Deciding what to roll, and how often, belongs on the
server.

## Summoning

The client never rolls. It asks for the banner list, asks for a banner's detail when you open it, and
when you confirm a pull it sends `GachaExeRequest` and renders the result the server names.

The entry request is the one that catches people out. `GachaEntryRequest` carries no banner id at
all — its body is the ordinary account envelope — and the banner catalogue rides the reply. The
banner layer is delivered this way, as response groups rather than as a master-data table the client
downloads. A reconstruction that puts the banners in the CDN will find the summons screen empty.

The pull's request body is small: the banner id and detail id, a repeat count (one or ten), and the
ticket id if the player chose one. The reply carries the awards as a list of `type:id` entries, where
type 10 is a unit, plus the refreshed currency balances. The banner, its cost and its pool are all
server-supplied; the client's own tables hold only the title text, keyed by the gacha id.

The cost is a small grammar, `kind:itemId:amount:count`, comma-separated for multiple entries. Kind 50
is lapis and 51 is friend points, and an empty cost is free because the amount defaults to one. Serve
exactly one entry per banner: a multi-entry cost does not produce the single-and-multi buttons, it
aborts the client on the summons screen with an uncaught range error.

Two things from our runs are worth passing on. The pull request's repeat-count and ticket-id fields
swap names in the reply class, so reading the request's fields with the reply's meanings miscounts the
pull — the kind of mistake that only shows up live. And banner artwork is fetched as a loose file, so
a miss there surfaces as the client's generic "a connection error has occurred" rather than as a
missing image. In our first run with a large generated catalogue, a handful of 404s on filenames
containing spaces read for a while as a broken network path, not as an asset problem.

The banner layer's internals are the subject of `gacha_endpoints.md`: which response groups build a
banner, how its tabs and buttons are chosen, and which parts a server has to author because they were
never in the APK.

## The home screen's recurring polls

Once the home screen is up, a small set of requests repeats on a timer. Their replies are trivial, and
the interesting part is what makes them stop.

Each routine reply carries a single value: a number of seconds until the client should ask again. Fill
in a positive delta and the poll goes quiet for that long. Return zero, or omit it, and the client
treats the answer as "ask again now" — which is why an unanswered or empty poll shows up as a request
repeating roughly once a second rather than as a single stalled request. The client has one of these
for each of its home, event, world and raid menus; the first three are the ones in the table above.

Notices work the same way at the request level. The request carries a kind, the reply's list is read
into the notice model, and an empty list is safe: every consumer guards the count, so "no notices"
renders as nothing rather than as a failure.

One envelope detail matters here. Tags are shared, and more than one tag can construct the same
response class, so a reply that carries two of them runs the class's callback twice. Send one.

## Party, units, friends and mail

The edit requests in this group are mostly echoes: the client sends a party-deck edit or a unit-equip
and expects an acknowledgement, and replying with the account record alone is accepted. The unit-equip
family also has an optional equip group; its reply class is `UnitEquipResponse`, which the factory
binds to eighteen tags, and the one our equip edits are answered with is `TJ9eL80N`.

What actually matters is state that has to be right before the edit. The active party id in the
account reply has to name a deck that exists in the same reply; a deck under one id and an active id
left at zero crashes the client inside the home screen. Decks also number from zero, and a deck list
that starts at one passes the home screen and then fails on the Units screen, which asks for deck zero
by index. Both are one-field mistakes with a whole screen between them and the cause.

For friends and mail, an empty list is the working answer: an empty friend list and an empty mail list
both render without trouble. There is one caveat to the general "empty is fine" rule. The full-list
replies clear their target list before adding to it, so replying with an empty list does not mean
"leave the old list alone" — it means an empty list. That distinction matters anywhere a list is
already populated.

The friend-list rows themselves are a separate caution: every field that response class reads is
optional display data with no verified reader, and populating the list faulted the friends scene in our
runs, so an empty list is the working answer there too. `support_and_friends_endpoints.md` has it.

## The shop

Entering the shop sends `PurchaseSettingRequest`, and its reply is where the age gate opens. The
reply has to carry the account's birth year and month; without it the gate never opens and the client
re-sends the request on every shop entry. There is a trap worth spelling out: the request's own group
name is also a tag that constructs a different response class, so a reply addressed to what the
request sent lands in the wrong object. Answer the setting response's own tag, not the request's.

`PurchaseListRequest` follows, and an empty list makes the shop render bare but working. Populating it
leads into the Play billing path, which is a build-and-platform problem rather than a server one.

## The support list, the arena and the emblem paths

Three further flows have been driven since this note's first version, each with its own note.

The **support list** — the units a battle can borrow — rides the `GetReinforcementInfoRequest` reply
rather than a screen request of its own. Its response class binds two tags, one that carries rows and
one that clears them, and an empty list is accepted. The caution is in the rows: they have to be built
from that response class's own field names, and a row built from a neighbouring class's set faults the
support-select layout. `support_and_friends_endpoints.md` has the row, the vision-card class it depends
on, and the espers that ride the same state.

The **arena's door** (`RbEntryRequest`) and the **Colosseum's** (`ClsmEntryRequest`) are
acknowledgements, but the screens they open read state delivered earlier. The arena's ranking screen
draws one orb button per orb up to the cap it was served, so a cap larger than the client's ten
laid-out buttons crashes it, and the orb values themselves ride the team-info reply.
`arena_and_colosseum_endpoints.md` has both failure modes and the four orb families.

The **emblem screens** are an entry request that returns the owned list and a setting request that
names the crest to display, with the campaign behind `sgEmblemEventRequest`.
`events_and_unlocks_endpoints.md` covers them, the event gate list and the story switches that open
locked feature tiles.

## Where the field maps are not

Everything above stops at the request and the shape of the reply. The eight-character response tokens
are not published here, so a server built from this note can be routed to and will be called — but its
replies still have to be filled in.

That is deliberate. Those maps are recoverable from the binary by the same method that produced the
endpoint table, and the contract's last section describes it. If you get stuck on a particular screen,
the shape of the answer is usually visible in what the screen does when the reply is empty, which is
how most of the notes behind this document began.
