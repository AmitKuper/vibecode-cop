# Public ingress: how our MCP doors are reached

Two paths reach the **same** two local listeners — cop on `61224`, thief on
`61223`. Only the URL we *declare* to the opponent changes; gameplay is
byte-identical either way.

| path | declared URL | needs |
|---|---|---|
| ngrok (opt-in) | `https://<tunnel-host>/mcp` | the ngrok agent running |
| **static** (default) | `http://62.56.220.143:<port>/mcp` | the router port-forward |

## The default is static, and that is deliberate

Both doors are permanently reachable on the static IP, so an opponent can probe
us hours before T, nothing has to stay running between games, and a restart
never changes an address we have already put in writing. The free ngrok plan
can only ever tunnel **one** of the two doors (see below), so choosing it as the
default would mean declaring a mixed pair for no gain — and tunneling both doors
properly (per-role paths / a second domain) is a **paid** feature, an ongoing fee
the static IP makes unnecessary.

**The tunnel path is tested end to end with OUR OWN door behind the tunnel,
not theoretical.** On 2026-08-24 a full six-window bench series was played with
our cop door served through a live ngrok tunnel
(`https://wilt-habitant-reopen.ngrok-free.dev` → `localhost:61224`) while the
thief door stayed on the static path — exactly the mixed pair the free tier
forces. The realistic peer simulator (`scripts/peer_sim.py --cop-door-url
<tunnel>/mcp`) dialed every cop window through the tunnel: **6/6 mutual audits
`Verified OK`**, cop captures in all three tunnel-served windows (sg2/4/6),
and ngrok's inspection API (`:4040/api/requests/http`) showed the `/mcp`
commit-reveal traffic traversing the tunnel. Earlier evidence layers: the
agent was first live-verified on 2026-08-14 (the single-domain endpoint-pool
behavior and the `ERR_NGROK_9038` path rejection below are empirical findings
from that session); the resolution/fallback logic is pinned by
`tests/test_ingress_default_ngrok.py`; and as the *dialing* side our wire also
crossed an opponent's real ngrok tunnel in counted game 9 (vm__fabi, won
90-30, their `cop-rob-p2p.ngrok.app` endpoint).

**Static-IP ingress is a deliberate, configured choice — not the path of
least resistance.** Supporting it required operator-side network
administration: defining **two port-forwarding rules in the router** (public
`62.56.220.143:61224` → the match host's cop door, `:61223` → the thief door)
and keeping those addresses stable across every declared pairing. In exchange,
both doors are simultaneously and permanently reachable with no third-party
dependency and **no subscription fees** — whereas serving both doors over
ngrok requires a paid plan (the free tier tunnels one door and load-balances
extra endpoints randomly). Tested tunnel, chosen static: a preference backed
by measurements, not a gap.

Turn ngrok on per pairing with `ingress = "ngrok"` in that opponent's profile —
useful when a peer cannot reach a high port and needs HTTPS on 443.

When ngrok *is* selected, `scripts/live_match_ref3.py --match` starts the agent
itself before declaring anything (`ref3_match/ingress_boot.py`); a running agent
is reused, never restarted mid-session. **If anything about ngrok fails the match
still runs** — we declare the static IP and print the reason.

Run it by hand only when you want the tunnel up early (for example so an
opponent can probe us before T):

```bash
# from the workspace root
ngrok start cop \
  --config "$LOCALAPPDATA/Packages/ngrok.ngrok_*/LocalCache/Local/ngrok/ngrok.yml" \
  --config tools/ngrok_tunnels.yml
```

Check what we would declare right now:

```bash
cd vibecode-cop
uv run python -c "import sys; sys.path.insert(0,'scripts'); \
from league_artifacts.core import our_mcp; print(our_mcp())"
```

## Start ONE tunnel, not two

The free plan grants **one dev domain**, and ngrok assigns it to every endpoint
we start — even one whose config names no domain at all (verified 2026-08-14).
The plan's "up to 3 online endpoints" all point at that single domain, which
makes them an **endpoint pool**: ngrok load-balances traffic across them at
*random*. So `ngrok start --all` does not give us two doors; it gives one URL
that lands on the cop door about half the time and the thief door the rest, mid
series, silently. That is worse than a deterministic mix-up and far harder to
diagnose from the opponent's side.

Separating the two roles by path (`/cop`, `/thief`) needs Cloud Endpoints with a
Traffic Policy — a paid feature. The agent rejects a path in an endpoint URL
outright on this plan (`ERR_NGROK_9038`). A second HTTPS door therefore means
paid ngrok or cloudflared (free, stable hostname, needs a domain you control).

The resolver refuses to guess: **any URL claimed by more than one local port is
discarded** and that role falls back to the static IP
(`league_artifacts/ingress.py::_drop_collisions`). So the practical setup is
`ngrok start cop` — cop tunnelled, thief on the static IP. That mixed pair is
what we played a full verified 6/6 series on.

A second HTTPS hostname needs a paid ngrok plan or cloudflared.

## Resolution order, per role

1. an explicit `our_<role>_mcp_url` in the pairing profile — always wins;
2. the live tunnel for that role's port, read from the agent's local API
   (`http://127.0.0.1:4040/api/tunnels`);
3. the static IP.

URLs are read from the running agent rather than hardcoded because the second
tunnel's hostname is **random on every start**.

## Choosing per pairing

`config/runtime.toml` sets the default:

```toml
[network]
ingress = "static"    # or "ngrok"
```

Any `config/opponents/<group>/runtime.toml` may override it, or pin exact URLs
with `our_cop_mcp_url` / `our_thief_mcp_url` (useful when an opponent has
whitelisted a specific host).

## Tunnel definitions

`tools/ngrok_tunnels.yml`, in the workspace root — deliberately **outside both
repos**, and it holds no secrets: the authtoken lives in ngrok's own config.
`cop` is pinned to the account's static domain; `thief` is defined for the day a
second hostname is available.

## Troubleshooting

**"ngrok did not report tunnel 'cop'"** — usually the authtoken config was not
found, so the agent started with no credentials and exited. A Microsoft Store
install redirects it into
`%LOCALAPPDATA%\Packages\ngrok.ngrok_*\LocalCache\Local\ngrok\ngrok.yml`;
`_default_config()` searches there too. Confirm with `ngrok config check`.
Passing `--config` for our tunnels *replaces* the default set, which is why the
authtoken file must be passed explicitly alongside it.

**Opponent gets a 502/530 from our tunnel** — the edge is up but the door behind
it is not; our workers only listen while a match is running.

**Declared URL looks wrong** — run the `our_mcp()` snippet above. It prints the
same decision the match makes, including the reason for any static fallback.
