# Public ingress: how our MCP doors are reached

Two paths reach the **same** two local listeners — cop on `61224`, thief on
`61223`. Only the URL we *declare* to the opponent changes; gameplay is
byte-identical either way.

| path | declared URL | needs |
|---|---|---|
| **ngrok** (default) | `https://<tunnel-host>/mcp` | the ngrok agent running |
| static | `http://62.56.220.143:<port>/mcp` | the router port-forward |

## You do not normally run any command

`scripts/live_match_ref3.py --match` starts the tunnel itself before it declares
anything (`ref3_match/ingress_boot.py`). If the agent is already running it is
reused, never restarted mid-session. **If anything about ngrok fails, the match
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

The free tier grants **one static domain**, and ngrok injects it into every
tunnel that does not name its own URL. `ngrok start --all` therefore makes the
cop *and* thief tunnels advertise the same hostname while only the last
registration actually routes — an opponent dialling our "cop" URL would land on
the thief door and the series would fail in a way that looks like a protocol bug.

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
ingress = "ngrok"     # or "static"
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
