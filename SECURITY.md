# Security policy

## Reporting a vulnerability

Please report vulnerabilities privately, through GitHub's
[private vulnerability reporting](https://github.com/ianderso/gov-gazetteer-mcp/security/advisories/new)
(the **Report a vulnerability** button on the repository's Security tab), not
in a public issue. Include what an attacker controls, what they gain, and the
steps to reproduce it.

You should hear back within a week. Fixes are released for the latest version
only.

## Scope

In scope: this server — the requests it makes, the files it writes (its
cache), and anything a tool argument or GOV's response can make it do.

Out of scope: GOV itself, which this project does not operate. Report
problems with GOV to its administrators (gov@genealogy.net) or the Verein für
Computergenealogie.

## The security model, briefly

- **No credentials.** GOV's web services need none. The server holds no key
  and sends none.
- **Tool arguments are treated as the attacker's.** A model writes them, and
  the model reads GOV's names and notes, and other pages, that may carry
  injected instructions. Everything below is about what such an argument can
  make the server do.
- **One endpoint, fixed in code.** Every request is a POST over https to
  `https://gov.genealogy.net/services/ComplexService`. A request hook refuses
  any other scheme, host, port, path or method, so an argument can choose
  only what is asked, never where it is sent. An argument that looks like an
  address is accepted only as a GOV page address, from which the id alone is
  kept.
- **Read operations only.** Envelopes are built for seven read operations
  (`getObject`, `getObjectByExternalId`, `getChildObjects`, `searchByName`,
  `searchByNameAndType`, `searchDescendantsByName`, `getTypeDescription`).
  GOV's ChangeService, which edits the gazetteer, has no envelope here.
- **Public addresses only, checked at connect time.** The transport resolves
  the host itself, refuses the connection if any address is private,
  loopback, link-local, shared (CGNAT), multicast, reserved, unspecified or
  site-local, in IPv4 or IPv6 (an IPv4-mapped, 6to4 or NAT64 address is judged
  by the IPv4 address inside it), and connects to the address it checked.
  Proxy settings in the environment are not used: through a proxy, the proxy
  would choose the address. Redirects are never followed.
- **Bounded answers.** An answer over 10 MB is refused as it streams in,
  whether or not its size was declared.
- **No entity expansion.** An answer carrying a document type declaration or
  an entity declaration is refused before the standard library's parser sees
  it; SOAP forbids both.
- **Arguments are validated** — GOV ids and external ids against narrow
  patterns, years as whole numbers in range, types against GOV's table —
  before they are placed in a request, and all text is XML-escaped.
- **Local writes.** The cache lives under `GOV_GAZETTEER_CACHE_DIR`, in files
  named by a hash of the request and written atomically. Nothing else is
  written.
- **GOV's responses carry untrusted text.** Names and notes are written by
  volunteers and reach the model verbatim, which makes them a channel for
  prompt injection. The server's instructions tell the model to treat that
  text as material, not as instructions, but the model still decides what to
  do next. An injection that leads the model to misuse this server's own
  tools is in scope; one that leads it to misuse other tools the client has
  connected is a client concern.
- **`GOV_GAZETTEER_CONTACT` is checked** for newlines and parentheses before it
  is placed in the User-Agent header.
