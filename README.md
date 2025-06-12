#main# agentsitter.ai

`A baby sitter for your agents.`

Agent Sitter is a layer 7 proxy [sitter] and an approval engine [app]. 

The `sitter` intercepts and monitors your AI agent's http / https traffic and detects risky / suspicious activity. When the `sitter` detects a risky action, it redirects your agent to a waiting page and submits the approval to a human via the `app`.

To install and configure agent sitter use the `sittr` cli.

Any AI agent with access to the web can be babysat by agentsitter. This repo focuses on [browser-use](https://github.com/browser-use/browser-use/) agents but more examples will be added soon.

## System Requirements

Linux / OSX - for windows support see / vote for [this issue](https://github.com/phact/agent-sitter/issues)


## Getting started

### Examples

#### Local `browser-use`

run the interactive initialization:

    uvx sittr init

or

    pipx sittr init


select local, install certs, and start the tunnel.

```
uvx sittr init
Initialize for which environment? [local/docker] [local]: local
Fetch & install CA certificate? [y/N]: y
Fetched CA certificate to /home/tato/Desktop/agent-sitter/ca-cert.pem
Imported CA into NSS DB for Firefox/Chromium
Start the local stunnel? [y/N]: y
Error response from daemon: network agent-sitter-net not found
No Docker bridge bind (network not found).
Stunnel started.
Open the dashboard in your browser? [y/N]: n
Skipped: Open the dashboard in your browser
Open the token URL? [y/N]: n
Skipped: Open the token URL
```

`sittr status` should show the certs installed and tunnel started, run:

    uvx sittr status

or

    pipx sittr status


```
$ uvx sittr status
Tunel started: ✅
CA certificate trusted: ✅
Docker network 'agent-sitter-net' exists: ❌
```

Then you're ready to run browser-use: 

clone the repo or download the example script:

    git clone git@github.com:phact/agent-sitter

and run:

    uvx --with browser_use python browser-use.py

Your agent will begin to browse the web, when a request hits the filter your approval will appear in the `app` at [agentsitter.ai](https://www.agentsitter.ai)

The `app` will prompt you to allow notifications. We will only notify you when an agent's actions trigger the `sitter` filter.

### Sitter Filter

Currently the filter simply flags any POST requests. Stay tuned for filtering customizations.

### Next steps:

[x] - `browser-use` local example
[ ] - enhanced filtering support
[ ] - `browser-use` docker example
[ ] - openai `cua` example
[ ] - anthropic `computer-use` example
[ ] - `sitter` local mode
