# Finding the endpoints

The other notes in this directory are results: the endpoint table, the boot path, the flows that have
been driven. This one is the method behind them, written so it can be repeated on a different build. We
work on the global v9.0.0 client; the method is the part that transfers to another edition.

It is deliberately platform-neutral. It names the files, the symbols and the observations, not the
emulator, the operating system or the tooling, because those are yours to choose. Nothing here depends
on Linux.

## What you need

Two things: the client package, so you can read its binary and its data, and a way to run the client
pointed at a machine you control, so you can watch what it asks for.

From the package, three trees matter:

- the native game library — `lib/arm64-v8a/libgame.so` in the Android package. Almost everything below
  lives here: the request classes, the response factory, the payload parsers. Editions differ, so
  confirm the name before assuming; it is the large ARM64 shared object.
- the Java half — `classes*.dex`. The crypto envelope and part of the HTTP layer live here, not in the
  native library, which is why a search of the native code for the cipher finds nothing useful.
- the data tree the game reads at run time — the master-data tables under `assets` and `files`. Useful
  for the tables that are shipped, and for recognising what is not.

For the live half, the client has to run with its traffic going to your host. It verifies TLS with the
platform default and does not pin, so a certificate authority you control, installed in the device's
**system** trust store, plus a redirect of the game host, is enough. A rooted device or emulator is the
straightforward route; a repackaged client is the fallback. That is setup, and it is the part this note
does not do for you.

## Part 1 — The request table, from the binary

### The three accessors

Every request class exposes three tiny methods:

- `getRequestID()` — the action's identifier
- `getEncodeKey()` — the per-request key
- `getUrl()` — the endpoint path

They are virtual, they are exported, and they are in the dynamic symbol table, so listing them is a
symbol lookup. In our build the mangled names have exactly this shape:

```
_ZN15GachaExeRequest12getEncodeKeyEv
_ZN15GachaExeRequest12getRequestIDEv
_ZN15GachaExeRequest6getUrlEv
```

Any ELF-aware tool reads that table: `nm -D`, `readelf --dyn-syms`, `pyelftools`, or simply opening the
library in Ghidra, which handles ELF on Windows, Linux and macOS alike. In our v9.0.0 build there are
**224** `getRequestID` implementations and **224** `getEncodeKey` ones; `getUrl` is a little more common
because some scene classes expose one too.

### The stub

Each of the three compiles to the same three instructions: load a string, return it.

```
adrp  x0, #<page>
add   x0, x0, #<offset>
ret
```

The first two build the address of a null-terminated string; `ret` hands it back. There is no
computation and no indirection. For `getUrl` the string is the path, `/actionSymbol/<8-char token>.php`;
for the other two it is the 8-character token itself.

The three stubs are adjacent in the function table — `getRequestID`, then `getEncodeKey`, then `getUrl`,
twelve bytes apart — so once you have one address you have all three for that class.

Two practical notes. The literals live in `.rodata`, and in our build the virtual address equals the
file offset for `.text` and `.rodata`, which is why a script can read them straight out of the file; do
not assume that of another build, since a real disassembler resolves them anyway. And the response
factory described below is reached through a PLT stub, so resolve its address from the relocations
rather than hard-coding an address that will not exist in your build.

### Doing it without symbols

If your build is stripped, the strings survive. Every endpoint is a literal matching
`/actionSymbol/<token>.php`, so you can enumerate those directly and then find which class references
each one; the `adrp`/`add` that loads it sits in a vtable slot, and the neighbouring slot or the RTTI
name gives you the class. Expect the count of classes to exceed the count of paths: **ten paths are
shared** by two or three classes, and a server that routes on the path alone will answer the wrong
request about one time in ten. Route on the decrypted body as well.

### What you get, and what changes per edition

You get, per class, a request-ID token, an encode key and a path. The path has the same shape in every
edition; the tokens do not. They are compiled-in constants and have to be recovered afresh for the JP or
Memorial build — do not carry the global tokens across. The method is the same, the table is not.

The response side is separate and worth recovering alongside. `GameResponseFactory::createResponseData`
is a `strcmp` chain mapping each incoming reply tag to the response class that will read it; the class is
the constructor called immediately after the allocation. That map is what tells you *which tag* to put
on a reply, and it is not the same list as the request identifiers: the client parses by tag,
independent of what it asked for. The payload fields inside each class come from `*Response::readParam`,
which compares incoming field names against 8-character tokens and branches to a store. Joining those
token-to-offset pairs to the sibling table struct's named accessors turns a token grid into a schema.
The longer notes behind this directory were all produced that way.

## Part 2 — Watching a live client

Reading the table tells you what the client *can* call. Watching it tells you what it *does*, and in
what order. The two together are what let you answer a screen.

### The tap

Stand up a server on the machine the client now points at. Arming is the redirect plus that server;
monitoring is its log. Per request it does four things, and each is a line:

1. read the path, and look the token up in the table you recovered — this names the class;
2. take that class's encode key, and decrypt the body with it and the fixed IV (the value is in the
   contract's envelope section);
3. write the decrypted body and the envelope to a per-request record;
4. answer it, or record that it did not.

The fourth point is the one that matters. A request received and a request answered are different
events, and the log has to distinguish them; ours prints `reply:sent` or `reply:none` and the key that
answered. Without that split you cannot tell "the client never asked" from "we never answered", and on
screen those look identical.

Decrypting the body needs the key from Part 1, which is why a synthetic server is a better first tap
than a TLS proxy. A proxy sees the ciphertext and the envelope, but the body is encrypted at the
application layer too, so a proxy on its own still cannot read it.

### The symptoms, and pinning them to a call

The visible failure is the client's connection-error dialog — "A connection error has occurred" in the
build we watch. It is raised by the connector, which ORs two conditions: a reply the native parser
could not parse, and a transport failure from the Java HTTP layer. Its button re-sends the *same*
request, not a fresh boot.

There is a second pattern, and it is the more useful one. When a request gets no reply at all, the
client re-sends the identical request on about a one-second tick. A request the server never answers
therefore does not sit stalled — it repeats, at a steady interval, with the same body.

That gives the pinning rule:

- a request repeating about once a second in the server log, or a `reply:none` line, *is* the call the
  screen is stuck on;
- the class and request-ID on that line name it;
- the timestamp of the first occurrence, next to the last screen transition you saw, tells you which
  action triggered it.

If several requests are in flight, the interval and the order separate them. In practice the repeating
one is unmistakable, because the healthy requests each happen once.

The other half of the pin is what the client expected back, which is the response tag from the factory
map. When there is no reply for a request, the quickest way to find the right tag is to see which tag
that screen reads — or, if you are set up for it, to watch the client resolve tags as you click. A hook
on the factory, or on the Java HTTP bridge beneath it, shows the tag the client is looking for and the
bytes the parser actually received. Both are worth having when a reply looks correct on paper but is
ignored in practice. Frida does this on Linux, Windows and macOS; any hooking tool that can reach the
Java and native layers will do.

### The loop

From there it is a loop, and a deliberately small one:

1. run to the failure;
2. read the server log for the repeating or unanswered request;
3. name the call from the recovered table;
4. find the response tag the client wants, and serve the smallest reply that satisfies it;
5. run again.

Empty replies are accepted surprisingly often — a list that is allowed to be empty, a delta of zero.
Where empty is not enough, the screen's own behaviour when the reply is empty usually shows you the
shape that is missing. Every note in this directory that begins "the reply has to carry" began as a
`reply:none` line and a screen that would not advance.
