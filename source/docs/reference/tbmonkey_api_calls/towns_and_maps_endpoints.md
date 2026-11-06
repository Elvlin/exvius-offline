# Towns and maps

Two halves of the same screen. A town or a field is entered, moved through and left with a handful of
small action requests, and the place itself — the map, its script, its dialogue, its music — is a pack
the client downloads, not something a reply can carry. A server has to do both: answer the action traffic
and be a file host for the packs.

This note covers the requests and the resource delivery underneath them. The packs are also where the
real gaps are: the client asks for every location's pack by exact name, and a large part of the
live-service layer no longer exists anywhere we can find. `missing_cdn_packs.md` is the list.

## The town requests

| Request class | request-ID | encode key | URL token | reply |
|---|---|---|---|---|
| `TownInRequest` | `8EYGrg76` | `JI8zU5rC` | `isHfQm09.php` | an acknowledgement (below) |
| `TownOutRequest` | `sJcMPy04` | `Kc2PXd9D` | `0EF3JPjL.php` | an acknowledgement |
| `TownUpdateRequest` | `G1hQM8Dr` | `37nH21zE` | `0ZJzH2qY.php` | an acknowledgement |
| `MissionUpdateRequest` | `j5JHKq6S` | `Nq9uKGP7` | `fRDUy3E2.php` | nothing is parsed from it |

The first three are the whole town transition: entering, leaving, and an update the town's own scenes
send while the player is inside. `TownInRequest` has been captured entering a town and `TownOutRequest`
leaving one; `TownUpdateRequest` is read from the binary and has not been observed on the wire.

The fourth row is the map-side twin. It is the same update without the town fields, and it is fired by a
map script rather than by a scene, so no single screen owns it. It has not been observed either — the
scripts that send it sit behind story switches.

## What the requests carry

- `TownInRequest` names the town and nothing else. It is the smallest of the four.
- `TownOutRequest` and `TownUpdateRequest` share one body: the town id, the switches being opened, the
  quest start and end state, and the field-treasure state. The three town classes and the map-update
  class all read the same body layout, so one description covers them.
- `MissionUpdateRequest` carries only the map-update block — no town id, because there is no town.

Above those fields the usual envelope groups ride along. The field-level wire keys are not published
here, as with the rest of the payload map; section 6 of `FFBE_SERVER_CONTRACT.md` is the method for
recovering them.

## What the reply has to satisfy

There is no town-state response class in the client. The only `Town*` response class in the binary is
the town's own master-data download, not an action reply, and the groups these four requests send are
absent from the response factory. Nothing in a reply to them is parsed into game state.

What does read the reply is the scene's connect check. It is the same check every scene inherits, and it
only asks whether a valid response arrived. So the requirement is structural, not semantic:

- **Any valid reply is enough.** In our runs the ordinary account record carries it; the client sends
  `TownInRequest` and stands on the town map.
- **No reply is a connection error.** That is the failure to look for. Entering the first town with no
  answer produced the client's generic "A connection error has occurred" — the same dialog a decode
  failure shows, with nothing pointing at the town.
- **`TownOutRequest` is a navigation gate.** The exit scene resolves the destination and pushes the
  next scene, but it waits for the acknowledgement before it navigates: no reply, no travel.
- **The account record has to be internally consistent**, because the same reply that clears the check
  also refreshes the player state. The active party id has to name a deck that exists in the reply, and
  decks number from zero. Both mistakes are one field wide and surface screens away; they are spelled
  out in `validated_endpoints.md`.
- **The update is optimistic.** The client has already applied its own inventory change before it sends
  `TownUpdateRequest`; the request is a report, not a query. A server that rejects or ignores the
  content will disagree with a client that has already moved on.

## The content is downloaded, not answered

No reply carries a town's layout, NPCs, script or music. Those arrive as one CPK pack per location,
fetched on demand while the client is entering it. The packs do not ship in the APK and are not part of
the full-download set; they are requested per location, which is why a copy of the game is only as
complete as the content its owner actually played.

### The URL

The host is the server's choice: the boot `GameSetting` reply carries it, and the client prepends the
scheme itself. That value has to be a **bare host** — writing `https://host/` into it produces
`https://https://host//…` and nothing downloads (this trap is in the README).

With the host correct, a pack URL has this shape:

```
https://<host>/common_lang/sd/<dir>/Ver<N>_<name>.cpk?v=<v>
```

`<dir>` and the bare `<name>` come from the client's own resource table (`F_RESOURCE_MAP_MST`), and
`<N>` is the version the client holds for that resource, taken from the map-resource version table
(`F_RESOURCE_MAP_VERSION_MST_LOCALIZE`). The client synthesises the `Ver<N>_` prefix itself — it is not
in any table — and appends a query value of its own; the packs fetched in our runs carry `?v=0`. A live
fetch reads, for example:

```
GET /common_lang/sd/event/11/Ver30_111010202.cpk?v=0
```

### What gets requested

Two pieces of server-supplied state decide it.

**The version reply names the packs.** Two response classes feed the client's download list: the
resource-version group (`ResourceVersionMstResponse`) on the mission and boot path, and the map-resource
version group (`MapResourceVersionResponse`). A pack reaches the scene's load list only if one of them
named it, with the version the client should hold. A pack already on disk at that version is not
re-fetched; advertise a higher version and the client pulls yours instead.

**The location's own table gates per-resource fetches.** `F_MAP_EXT_RESOURCE_MST` holds one row per
(town or mission, resource) pair, and the client's download popup walks those rows before the scene
loads. A row is requested **if and only if** its download switch is on **and** its ignore switch is off.
The switch strings have their own grammar: empty is false, the literal `0` is true and unconditional,
`a|b` is an OR over switch ids, and `a,b` is an AND. A row that fails the gate is never requested —
which is how a story beat normally holds a sub-scene back until the player has reached it.

That gate is also the one lever for a pack you cannot serve. Some rows are unconditional — no switch can
suppress them — and those are requested the moment the location loads. Granting a bit to skip one may
enable another, so suppression is not free; often the only workable answer is to make the download
succeed.

### When a pack is missing

A requested pack that 404s is **fatal to the location**, not a missing asset. The installer raises the
client's generic connection error and the scene never loads. If a town will not open and the log shows
the request retrying, look for the pack fetch before the reply.

Two things on top of that:

- **The load-list reply can only suppress.** `DungeonResourceLoadMstListRequest`'s reply
  (`DungeonResourceLoadMstResponse`) is a substring filter over the location's pack list, not a fetch
  list: a matching record that does not name a pack removes it from consideration, and an empty reply
  permits everything. Put content in it thinking it causes a download and the effect is the opposite.
  The mission-bundle use of the same request is in `validated_endpoints.md`.
- **A 200 is not a pack.** We caught a host returning HTTP 200 with a 243-byte error document where a
  pack should have been; a size check against the manifest accepted it. Check the magic: packs begin
  `CPK `, and the BGM `.acb` files the same rows name are CRI `@UTF` tables. A wrong-format file is as
  fatal as a 404.

Where a row cannot be suppressed and the pack cannot be obtained, a minimal **empty but valid CPK** at
the exact path keeps the location loadable — it invents no content, and the real pack replaces it at the
same path. Two of the town sub-scenes in `missing_cdn_packs.md` are held that way today.

## What is inside a pack

A map or event pack carries the scene's binary script (`map.bin` / `event.bin`) and its dialogue text.
The client loads the **localized** (`_sg`) text siblings only — `<id>_map_text_sg.txt` and
`<id>_map_teller_sg.txt` for a map, `<id>_event_text_sg.txt` and `<id>_event_teller_sg.txt` for an
event — and composes each dialogue key as `MAP_TEXT_<packId><textId>`.

The two text forms are not interchangeable:

| file | shape |
|---|---|
| `<id>_event_text.txt` | `key,text` — comma-separated, one language |
| `<id>_event_text_sg.txt` | `key^EN^ZH-TW^KO^FR^DE^ES^TH^ID` — caret, one row per text id |

A pack that carries only the single-language sibling leaves the client's text store empty and the
cutscene renders the raw key: `MAP_TEXT_111010202210045` in the dialogue box instead of the line. That
is not a missing string, it is a missing file variant. A server can repack the pack with the `_sg`
sibling added and serve it under a bumped version; the client fetches the new copy on the next load. In
our runs a repacked event pack rendered the real line after the client's cached copy was cleared, which
is the one step that is easy to forget.

## What has no source

The live-service layer was never in the APK, and the offline end-of-service builds we can compare against
pruned the time-limited content. Of the 4,206 packs the client's tables reference, 2,334 have no source we
can find — 418 playable-priority and 1,916 event-layer — and two more playable-priority packs are held
only by an empty placeholder. `missing_cdn_packs.md` lists the resulting 420 exact playable-priority paths
and the event-layer families, says what is already covered so an ask does not over-claim, and gives the
test for whether a copy of the game is worth contributing.

## What is not established

- **`TownUpdateRequest` and `MissionUpdateRequest` have not been seen on the wire.** Their bodies are
  read from the binary; the state the client sends is inferred from the shared body layout.
- **Whether the original server validated the update.** The client parses none of the request's fields
  back and applies its own state first, so nothing in the client enforces it. The honest assumption is
  that the server was free to ignore or audit the report; which it did is not recoverable from the
  client alone.
- **The request payload field keys** are not published here, per the rest of these notes.
- **What a story script's `map@<n>` selector indexes.** Story phases carry a map target of that form and
  the numbering is not a shipped table; mapping it is open.
