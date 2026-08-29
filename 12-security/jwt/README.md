---
topic: JWT
category: Security
difficulty: Intermediate
concepts: [tokens, signatures, revocation, claims, refresh-tokens]
related: [authentication, oauth, api-security]
---

# JWT — JSON Web Tokens

`[INTERMEDIATE]` · A signed, readable, self-contained claim set. **You cannot take one back before it expires without keeping exactly the server state you adopted JWTs to avoid — and that single fact should decide most of your design.**

---

## 1. One-line definition

A compact, URL-safe token in three base64url-encoded parts — header, payload, signature — where
anyone holding the verification key can confirm that the payload was issued by the signer and has
not been altered since.

## 2. Explain like I'm new

Think of a festival wristband with your name and ticket type printed on the outside and a hologram
that cannot be faked. Three properties follow, and all three matter:

1. **Anyone can read it.** The printing is on the outside. It is not a secret.
2. **Nobody can forge it.** The hologram is the signature.
3. **Nobody can un-issue it.** If you get thrown out, the wristband still says you belong here —
   until the festival ends.

Point 3 is the one that surprises people, and it is not a flaw in some implementations. It is what
"self-contained" means. The gate staff make their decision by looking at the band, not by phoning
the office — that is the whole speed advantage, and it is precisely why they cannot be told you were
ejected.

## 3. Real-world analogy

A printed boarding pass. It states your name, seat and flight; the barcode proves the airline
printed it; the gate agent can verify it without calling anyone.

**Where it breaks:** the airline *also* keeps a booking record, and the gate scanner checks it. Your
pass can be a valid, correctly-printed document and still be refused because the booking was
cancelled — which means the airline never actually had a stateless system. They have a
self-contained document *plus* a live list, and the document is an optimisation on top.

That is the honest model for JWTs in production. A pure JWT deployment has no list. The moment you
need one — and you will, the first time someone is offboarded — you have a session with extra steps.

## 4. Technical explanation

### Structure

```
base64url(header) . base64url(payload) . base64url(signature)

header    {"alg":"RS256","typ":"JWT","kid":"2026-03-a"}
payload   {"iss":"https://auth.example.com","sub":"u_1234",
           "aud":"api.example.com","exp":1735689600,"scope":"orders.read"}
signature RS256( base64url(header) + "." + base64url(payload), private key )
```

**Signed is not encrypted.** Base64url is an encoding, not a cipher — anyone who can see the token
can paste it into a decoder and read every claim. The encrypted variant (JWE) exists and is rarely
used. So the rule is blunt: **do not put anything in a JWT that you would not print on a postcard.**
No email addresses you would rather not leak into a log aggregator, no internal identifiers you
consider sensitive, no permission structures you would prefer attackers not to map.

### Registered claims, and what breaks if you skip one

| Claim | Meaning | Skip the check and |
|---|---|---|
| `iss` | Issuer | You accept tokens minted by a different, possibly attacker-controlled, issuer |
| `sub` | Subject — the principal | You have no idea whose token this is |
| `aud` | Audience — who it is for | **A token intended for another service or tenant is accepted by yours** |
| `exp` | Expiry | The token is valid forever |
| `nbf` | Not valid before | Minor; matters with clock skew |
| `iat` | Issued at | You cannot reason about token age or enforce a max session length |
| `jti` | Unique token id | You have nothing to put on a denylist |

`aud` and `iss` are the two most commonly skipped and the two that most often turn a valid token
from somewhere else into an authorisation bypass in your system.

### Algorithms

| `alg` | Kind | Who can mint | Use when |
|---|---|---|---|
| `HS256` | HMAC, shared secret | **Everyone who can verify** | One service issues and consumes its own tokens |
| `RS256` | RSA signature | Only the private key holder | Many verifiers — the normal choice for federation |
| `ES256` | ECDSA P-256 | Only the private key holder | Same as RS256, smaller tokens and keys |
| `EdDSA` | Ed25519 | Only the private key holder | Modern preference where supported |
| `none` | **Nothing** | Anyone | Never. It exists for unsecured JWTs and has caused real breaches. |

**The `HS256` property people miss:** with a shared secret, every service that can *check* a token
can also *issue* one. A compromised low-value read service can mint an admin token. Asymmetric
algorithms remove minting power from every verifier, and that is usually worth the extra bytes.

### The three classic attacks

| Attack | Mechanism | Fix |
|---|---|---|
| **`alg: none`** | Attacker strips the signature and sets the header to `none`. A permissive library returns the payload as verified. | Never let the token choose. Pin the accepted algorithm server-side. |
| **HS256/RS256 confusion** | Server expects RS256 and calls `verify(token, publicKey)`. Attacker sends an HS256 token signed with the **public key itself as the HMAC secret**. A library that picks its mode from the header treats the public key as a shared secret and the signature validates. The public key is, by definition, public. | Pin the algorithm; use APIs that take a typed key, not a byte string |
| **`kid` injection** | The key id is used to look up a key by path or database query. Attacker supplies `../../dev/null`, an SQL fragment, or a URL they control. | Allowlist key ids; never use `kid` as a file path or in a query |

Then the one that outnumbers all three in real code review: **calling `decode` instead of
`verify`**. Every library has both. `decode` parses without checking the signature, exists for
debugging, and reads identically to the safe version at a glance. Grep for it.

### Size

A realistic access token with a handful of claims is 500 bytes to 1 KB; add roles and permissions
and 2 KB arrives quickly. That is sent on **every** request. At 10,000 requests per second, a 1 KB
token is roughly 10 MB/s of pure header traffic, plus proxy buffer sizing, plus the 4 KB per-cookie
browser limit that you will eventually hit — usually in production, usually for the one user with
forty roles. **Claims bloat happens because adding a claim looks free**, and the request that
finally exceeds the limit fails in a way that looks nothing like "the token got too big".

## 5. Engineering at scale — revocation, which is the whole page

You cannot un-issue a signed token. Every option is a way of adding just enough state to make the
signature not the last word.

| Strategy | Revocation latency | State kept | Honest verdict |
|---|---|---|---|
| **Short expiry only** (5–15 min) | Up to the TTL | None | The only genuinely stateless option. Accept the window in writing, or do not use JWTs. |
| **Per-user token version / `not-before`** | Immediate | One integer per user | **Best value by a distance.** Cheap, cacheable, revokes all of a user's tokens at once. |
| **`jti` denylist** | Immediate | One entry per revoked token until its `exp` | Bounded and small — revoked tokens are rare. Good for single-token revocation. |
| **Introspection per request** | Immediate | Full session state | You have rebuilt sessions, with more moving parts and a slower lookup |
| **Rotate the signing key** | Immediate, for everyone | None | The nuclear option: logs out the entire user base. Keep it for key compromise. |

**Every row that revokes quickly is server state, and that is the honest framing of JWT: it does not
remove state, it lets you choose how much staleness to trade for a smaller amount of it.** Choosing
the second row — one integer per user, replicated into a cache your services already read — gives
near-immediate revocation for a fraction of a session store's cost. That is a good design. Claiming
it is stateless is not.

### Why refresh tokens exist

The refresh token is the direct consequence of the paragraph above. Because you cannot revoke an
access token, you make it short-lived; because short-lived tokens would log users out every ten
minutes, you issue a long-lived refresh token; and because the refresh token is presented **only to
the authorisation server** — which is stateful and *can* refuse — you get an enforcement point back.

**The refresh token is an admission that stateless authentication needs a stateful anchor.** Two
rules for it: rotate on every use, and detect reuse. If a refresh token that has already been
exchanged is presented again, either it was stolen or the legitimate client raced — treat it as
theft, revoke the entire token family, and force a fresh login. That single mechanism converts
"attacker has indefinite silent access" into "attacker gets one window and then everybody notices".

### Keys and clocks

Rotate signing keys on a schedule with `kid` in the header, publish both old and new in the JWKS
during an overlap at least as long as your maximum token lifetime, and only then retire the old one.
Retiring early invalidates every token in flight simultaneously — a self-inflicted total outage,
and one of the more common ways a JWT deployment falls over.

Allow 30–60 seconds of clock leeway on `exp` and `nbf`. Across regions and virtualised hosts, clocks
drift; a token minted one second in the future by a fast issuer and rejected by a slow verifier
produces intermittent, unreproducible authentication failures that will consume a week.

### Where to keep it in a browser

| Location | XSS exposure | CSRF exposure | Verdict |
|---|---|---|---|
| `localStorage` | **Readable by any injected script** | None | Popular, and wrong for anything that matters |
| `sessionStorage` | Same | None | Same problem, shorter lifetime |
| JavaScript-readable cookie | Same | Yes | Worst of both |
| **`HttpOnly` + `Secure` + `SameSite` cookie** | Not readable at all | Mitigated by `SameSite` plus a CSRF token | **The default** |
| In-memory variable only | Lost on reload; small window | None | Strong, paired with a refresh token in an `HttpOnly` cookie |

**"JWTs avoid CSRF" is a trade, not a win.** CSRF is solved by default in modern browsers via
`SameSite`; XSS token theft is not solved by anything except not letting scripts reach the token. A
JWT can live perfectly well inside an `HttpOnly` cookie — the cookie is transport, the JWT is
format, and the argument is usually conducted as though picking one excluded the other.

## 6. The problem it solves

Passing **verified claims between parties that do not share a session store** — across services,
across teams, across organisations. A resource server can authenticate a caller with nothing but a
cached public key: no shared database, no network call, no coupling to the issuer at request time.

That is a genuinely valuable property, and it is why JWTs won in service-to-service and federation.
It is a much weaker property inside a single application that already has a cache.

## 7. The problem it does NOT solve

- **Revocation.** The headline. See §5, and note that everything which fixes it is server state.
- **Confidentiality.** Signed, not encrypted. Every claim is readable by anyone holding the token.
- **Authorisation.** A `role: admin` claim is only as trustworthy as the issuer and as useful as the
  check you write. It certainly does not answer "may this user modify *this object*" — see
  [API security](../api-security/).
- **Sessions.** A JWT is an assertion with an expiry, not a session. It has no concept of activity,
  idle timeout, concurrent devices or "log out everywhere".
- **Freshness.** Claims are a snapshot from the moment of signing. Change a permission and the token
  still carries the old one until it expires. **Every JWT is stale on arrival**; the only question
  is by how much.
- **Independence from the auth service.** The refresh path still calls it.

---

## 9. How it works — the verification sequence

Every step is required, and each one exists because skipping it was somebody's incident.

1. **Split and decode.** Trust nothing yet. This is parsing, not verification.
2. **Check `alg` against a server-side allowlist.** Never select the key type from the token's own
   header. This closes `alg: none` and the HS256/RS256 confusion in one step.
3. **Select the key by `kid`** from an allowlisted, cached JWKS. Do not fetch per request; do not
   treat `kid` as a path or a query fragment.
4. **Verify the signature** over the header and payload **exactly as received** — the received bytes,
   not a re-serialised copy, because JSON round-tripping can change them.
5. **Check `exp` and `nbf`** with bounded leeway.
6. **Check `iss`** equals the issuer you expect.
7. **Check `aud`** contains you.
8. **Check revocation state** — token version, `jti` denylist, whatever you chose in §5.
9. **Only now** read the claims. Then authorise the action against the specific object.

**Steps 6 and 7 are the ones that get skipped**, and they are exactly what stops a valid token from
another tenant, another environment, or another service being accepted by yours. A staging token
working against production is the friendly version of this bug.

## 13. When to use it

- **Service-to-service claim propagation** — the caller's identity travels with the request through
  five hops without every hop calling the auth service. This is the strongest case.
- **Federated identity** — OIDC ID tokens are JWTs by specification. You do not get a choice, and
  the choice is correct.
- **Short-lived access tokens** where a few minutes of revocation lag is genuinely acceptable, and
  someone with authority has said so.
- **Inherently short-lived, single-purpose artefacts**: email verification links, password reset
  tokens, signed download URLs, one-time invitations. Bounded lifetime, single use, no revocation
  requirement — the sweet spot, and an underused one.

## 14. When NOT to

- **Browser sessions for a single first-party application.** A session cookie is simpler, smaller,
  revocable, and leaks nothing. See [authentication](../authentication/).
- **Anything requiring instant logout**: banking, admin consoles, anything with a regulator, and any
  product that ships a "sign out of all devices" button.
- **When permissions change often.** Roles baked into a token are wrong from the moment they change,
  and users will report it as a bug.
- **As a data store.** A JWT is not a place to keep the user profile. It grows, it goes stale, and
  it is public.
- **For anything sensitive in the payload.** Repeating it because it keeps happening: signed, not
  encrypted.
- **When you cannot articulate what it bought you.** If the answer is "it is stateless", check
  whether you are keeping a denylist. Usually you are.

## 17. Trade-offs

| Choose | Get | Pay |
|---|---|---|
| Self-contained tokens | Offline verification; no shared session store | No revocation before expiry |
| Short expiry | Small revocation window | Refresh traffic, and a hard dependency on the issuer being up |
| Long expiry | Fewer refreshes; survives an issuer outage | A stolen token stays useful for hours |
| `HS256` | Trivial setup, tiny cost | Every verifier can also mint |
| `RS256` / `ES256` | Verifiers cannot mint; keys distribute safely | Key management, JWKS, rotation |
| More claims in the token | Fewer lookups downstream | Bigger tokens on every request; more stale data; more exposure |
| `jti` denylist | Real revocation | The state you were avoiding, plus a lookup on the hot path |
| Token version per user | Real revocation, cheaply | Still state, and still a cache-propagation window |

## 18. Why not?

| Alternative | Why not here | When it WOULD win |
|---|---|---|
| **Server-side session** | Needs a shared store; awkward across organisations | One app, one domain — most software. Instant revocation for free. |
| **Opaque token + introspection** | A network call per request; issuer on your read path | You need immediate revocation and can afford the hop, or can cache it briefly |
| **Signed cookie** (framework-native) | Not interoperable across parties | Exactly the same idea with better defaults, when only your own app reads it |
| **PASETO / Branca** | Smaller ecosystem, less library support | You want the format without JWT's algorithm-agility footguns — a defensible choice |
| **mTLS** | Certificate lifecycle is real work; no user claims | Service-to-service inside your own infrastructure |
| **API key** | Static, no expiry, no claims | Machine callers where a scoped, rotatable secret is enough |

## 19. Failure scenarios

| Failure | What happens | Mitigation |
|---|---|---|
| **Employee offboarded, token still valid** | Access continues for the remaining token lifetime. The offboarding ticket is closed and everyone believes it is done. | Short expiry + per-user token version; revoke at the refresh endpoint |
| **Signing key compromised** | Anyone can mint any token, as anyone, and nothing in the logs looks wrong | Asymmetric keys, HSM or KMS storage, rehearsed rotation, short lifetimes |
| **Key rotated without overlap** | Every in-flight token fails at once — total outage from a routine maintenance task | Overlap old and new for at least the maximum token lifetime |
| **`aud` unchecked** | A valid token from another service or tenant is accepted | Verify `aud` and `iss`; fail closed |
| **Library accepts `alg: none`** | Trivial forgery | Pin the algorithm server-side; keep libraries current |
| **`decode` used instead of `verify`** | Signature never checked; every claim is attacker-controlled | Code review, linting, and a wrapper that only exposes the safe call |
| **Clock skew across regions** | Intermittent, unreproducible auth failures | 30–60 s leeway; monitor clock drift |
| **Token grows past a limit** | Requests fail at the proxy or the cookie is silently truncated | Cap claims; monitor p99 token size; keep permissions out of the token |
| **Refresh token stolen** | Indefinite renewal, invisible in login metrics | Rotation with reuse detection; revoke the family on reuse |
| **JWKS endpoint unreachable** | Nothing validates anywhere | Cache keys with a long TTL; serve stale keys rather than failing |

## 25. Without it → With it → New problem → Next

```
Without it   →  every service must call the auth service to learn who the caller
                is, or all of them must share one session store
With it      →  any service verifies the caller offline with a cached public key,
                and identity travels with the request across every hop
New problem  →  you cannot revoke a token before it expires; claims are stale from
                the moment they are signed; the payload is readable by anyone who
                holds it
Next         →  short expiry plus refresh tokens — and a revocation list or token
                version, which is precisely the server state you were avoiding
```

The last line is the honest ending, and it is why [sessions](../authentication/) deserve a fair
hearing before you commit. See [the chain](../../SYSTEM-DESIGN-THINKING.md#part-1--the-chain).

## 28. Common mistakes

| Mistake | Why it is wrong |
|---|---|
| **Assuming you can revoke one** | You cannot, without server state. Design for the window or do not use JWTs. |
| Putting sensitive data in the payload | Signed, not encrypted. Anyone holding the token reads it. |
| `decode` instead of `verify` | The signature is never checked; every claim becomes attacker input |
| Not pinning `alg` | `alg: none` and HS256/RS256 confusion |
| Not checking `aud` and `iss` | Tokens from another service, tenant, or environment are accepted |
| `HS256` shared across many services | Every verifier can mint; one compromise is total |
| Long-lived access tokens | Optimises away a refresh call and buys a multi-hour theft window |
| Roles and permissions in the claims | Stale on change, and the token grows past transport limits |
| No key rotation plan | The first rotation is attempted during an incident, and fails |
| `localStorage` for the token | Any XSS is a complete account takeover |
| Treating a JWT as a session | No idle timeout, no device list, no logout |
| Rejecting on `nbf` with zero leeway | Intermittent failures from ordinary clock drift |

## 29. Monitoring

**Split validation failures by reason and alert on them differently.** Expired tokens are normal
background noise. *Invalid signature*, *unexpected issuer* and *wrong audience* are attack or
misconfiguration signals, and folding them into a single `auth_failures` counter is how the
interesting one hides inside the boring one.

Also track: unknown `kid` rate — which means either a rotation went wrong or someone is probing;
refresh reuse detections, each one a probable theft; clock drift between issuers and verifiers; p99
token size, so claims bloat is visible before it becomes a 431; and the age distribution of tokens
being presented, which tells you the real revocation window rather than the configured one. See
[observability](../../11-observability/).

## 31. Exercises

**1.** Your service validates RS256 tokens by calling `verify(token, key)` where `key` is the
issuer's public key loaded at startup, and the library selects its algorithm from the token header.
Explain the exploit precisely, and say why the public key being public is the crux.

<details><summary>Answer</summary>

The attacker crafts a token with `"alg":"HS256"` and signs it using **the issuer's public key as the
HMAC shared secret**. Your library reads the header, sees HS256, and switches to symmetric mode. It
then treats the key material you passed — the public key — as the HMAC secret, recomputes the MAC,
and finds it matches. The token verifies. Every claim in it, including `sub` and any role, is
attacker-chosen.

The crux is that RSA public keys are *published*: in your JWKS endpoint, in your OIDC discovery
document, in the certificate chain. There is no secret involved anywhere in the attack. Anyone who
can read your discovery document can mint tokens.

The fix is to remove the token's ability to choose: pass an allowlist of acceptable algorithms
(`{algorithms: ["RS256"]}`) and reject anything else before verification. Better still, use a
library API that takes a typed key object rather than a byte string, so an RSA public key simply
cannot be interpreted as an HMAC secret — the type system refuses the confusion.

The general principle is worth more than the specific bug: **never let attacker-controlled input
select the security algorithm.** The same shape appears in content-type sniffing, deserialisation,
and file upload handling.
</details>

**2.** A team stores permissions in the JWT to avoid a database lookup per request. An admin removes
a user's `billing.write` permission. The user keeps writing billing records for 55 minutes. The team
proposes shortening the token to five minutes. Evaluate that fix.

<details><summary>Answer</summary>

It reduces the exposure from 55 minutes to five, at the cost of multiplying refresh traffic by
eleven. Whether that is a good trade depends on a number nobody in the scenario has stated: **how
long is a permission change allowed to take?** If the answer is "immediately", five minutes does not
satisfy it either — it just makes the violation shorter and harder to notice in testing.

The deeper problem is that permissions were put in the token at all. A permission is mutable state
with an authoritative owner; a token is an immutable snapshot. Baking one into the other guarantees a
staleness window forever, and the window is now coupled to token lifetime, so every future
performance decision is also a security decision.

The better shape: keep **identity** in the token (`sub`, `iss`, `aud`, `exp` — things that do not
change during a session) and resolve **permissions** at the point of use, from a cache with a TTL
you control independently and can invalidate on write. That is one cache read, typically well under
a millisecond, and it decouples "how often do users re-authenticate" from "how fast does a
permission change take effect".

Note the honest cost: you have added a lookup on the request path. That is the trade, and it is
almost always the right one, because the lookup is cheap and being wrong about permissions is not.
</details>

**3.** You are told a JWT is "secure because it is encrypted". Give the two-sentence correction, then
name one thing that goes wrong in practice as a direct result of the misunderstanding.

<details><summary>Answer</summary>

A standard JWT is **signed, not encrypted**: base64url is an encoding anyone can reverse, so every
claim is readable by anyone holding the token. The signature guarantees integrity and origin — that
the payload has not been altered and came from the key holder — and provides no confidentiality
whatsoever.

What goes wrong in practice: teams put things in the payload they treat as secret. Internal user
identifiers, email addresses, phone numbers, employment status, feature-flag entitlements that
reveal unreleased products, and the shape of the permission model itself. Those tokens are then
written to access logs, forwarded in `Referer` headers if they ever appear in a URL, cached by
proxies, shipped to a log aggregator with broad internal read access, and pasted into support
tickets. The confidentiality breach happens through ordinary operational plumbing, with no attacker
involved at any point.

The second-order failure is worse: a leaked payload tells an attacker exactly which claims your
system trusts, which is the reconnaissance step for the forgery attempts in exercise 1.
</details>

**4.** Your architect says "we use JWTs, so we are stateless, so we can scale horizontally without a
shared session store". Your product owner then requires that suspending an account takes effect
within one second. Reconcile these, and state what is actually true about the system afterwards.

<details><summary>Answer</summary>

They cannot both hold as stated. A one-second revocation requirement means every request must
consult something that changed less than a second ago, and a signed token cannot be that thing.

The cheapest reconciliation is a **per-user token version** (or a `not-before` timestamp) held in a
replicated cache and checked on every request: suspending an account bumps the integer, and every
token issued before it stops being accepted. One small read, microseconds from a local or nearby
cache, and it revokes all of a user's tokens at once rather than one at a time.

What is actually true afterwards, and worth saying out loud in the design review:

- The system is **not stateless**. It has shared state on the request path.
- What it has is *less* state than a session store — one integer per user rather than a full session
  record — and that state is read-mostly, tiny, and highly cacheable.
- Revocation is not instantaneous; it is bounded by cache propagation. Measure it and publish the
  number. If it is 200 ms, you meet the requirement; if replication is asynchronous across regions,
  you may not, and that must be discovered now rather than during an audit.
- The horizontal scaling claim survives intact, because a cache read scales differently from a
  session store write. That is the real benefit, and it was always a smaller and more specific claim
  than "stateless".
</details>

## 33. Related

- [Security overview](../README.md) — the section index
- [Authentication](../authentication/) — sessions versus tokens, presented as the genuine trade it is
- [OAuth 2.0 + OIDC](../oauth/) — where most JWTs come from, and why the ID token exists
- [API security](../api-security/) — a valid token is the beginning of authorisation, not the end
- [Caching](../../04-caching/fundamentals/) — a revocation cache is a cache, with the usual staleness trade
- [Reliability](../../00-foundations/reliability/) — key rotation and JWKS outages are reliability events
- [Observability](../../11-observability/) — split validation failures by reason or you will see nothing
- [Glossary](../../GLOSSARY.md)
