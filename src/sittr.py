#!/usr/bin/env python3
"""
sittr CLI tool for AgentSitter.ai
"""
import os
import sys
import socket
import json
import subprocess
import webbrowser
import shutil
import typer
from pathlib import Path

app = typer.Typer(help="AgentSitter.ai CLI (sittr)")

DEFAULT_PROXY_HOST = "localhost"
DEFAULT_PROXY_PORT = 8080
DEFAULT_DASHBOARD_URL = "https://www.agentsitter.ai"
DEFAULT_TOKEN_URL = "https://www.agentsitter.ai/token/new"
CERT_URL = "https://agentsitter.ai/certs/ca-cert.pem"
CERT_PATH = Path.cwd() / "ca-cert.pem"
NETWORK_NAME = "agent-sitter-net"
BASHRC_PATH = Path.home() / ".bashrc"


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

@app.command()
def init():
    """
    Interactive initialization: choose local or docker, then
    run cert-install, tunnel-start, dashboard & token (local),
    or docker-network-setup, tunnel-start, dashboard & token (docker).
    """
    # 1) Ask which environment
    env = typer.prompt("Initialize for which environment? [local/docker]", default="local")
    env = env.lower().strip()
    if env not in ("local", "docker"):
        typer.secho(f"Invalid choice '{env}', defaulting to local.", fg=typer.colors.YELLOW)
        env = "local"

    # 2) Build the list of (description, function) steps
    if env == "local":
        steps = [
            ("Fetch & install CA certificate", cert_install),
            ("Start the local stunnel", tunnel_start),
            ("Open the dashboard in your browser", dashboard),
            ("Open the token URL", token),
        ]
    else:
        steps = [
            ("Create Docker network & iptables rules", docker_network_setup),
            ("Start the local stunnel", tunnel_start),
            ("Open the dashboard in your browser", dashboard),
            ("Open the token URL", token),
        ]

    # 3) Iterate, asking y/n for each
    for description, action in steps:
        if typer.confirm(f"{description}?"):
            action()  # call the command function directly
        else:
            typer.secho(f"Skipped: {description}", fg=typer.colors.YELLOW)

def cert_installed() -> bool:
    """Return True if the agent-sitter CA is present."""
    if sys.platform.startswith("linux"):
        nssdb = Path.home() / ".pki" / "nssdb"
        res = subprocess.run(
            ["certutil", "-L", "-d", f"sql:{nssdb}", "-n", "agent-sitter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    elif sys.platform == "darwin":
        res = subprocess.run(
            ["security", "find-certificate", "-c", "agent-sitter"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        return res.returncode == 0
    return False

def token_present() -> bool:
    """Return True if AGENTSITTER_TOKEN is in env or bashrc."""
    if BASHRC_PATH.exists():
        for line in BASHRC_PATH.read_text().splitlines():
            if line.strip().startswith("export AGENTSITTER_TOKEN="):
                return True
    return False

def remove_token_from_bashrc():
    """Remove any AGENTSITTER_TOKEN export lines from ~/.bashrc."""
    if not BASHRC_PATH.exists():
        return
    lines = BASHRC_PATH.read_text().splitlines()
    new = [l for l in lines if not l.strip().startswith("export AGENTSITTER_TOKEN=")]
    BASHRC_PATH.write_text("\n".join(new) + "\n")
    typer.secho("Removed AGENTSITTER_TOKEN from ~/.bashrc", fg=typer.colors.GREEN)

def network_exists() -> bool:
    """Return True if the Docker network is present."""
    res = subprocess.run(
        ["docker", "network", "inspect", NETWORK_NAME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    return res.returncode == 0

def tunnel_running() -> bool:
    """Return True if stunnel is currently running."""
    return subprocess.run(
        ["pgrep", "-f", "stunnel"], stdout=subprocess.DEVNULL
    ).returncode == 0

@app.command()
def cleanup():
    """
    Interactive cleanup: remove cert and/or Docker network, if present.
    """
    steps = []

    if tunnel_running():
        steps.append(("Stop the local stunnel", tunnel_stop))
    else:
        typer.secho("No stunnel process found; skipping tunnel stop.", fg=typer.colors.YELLOW)
    if cert_installed():
        steps.append(("Remove the AgentSitter CA certificate", cert_remove))
    else:
        typer.secho("No AgentSitter CA certificate found; skipping cert removal.", fg=typer.colors.YELLOW)

    if network_exists():
        steps.append(("Tear down Docker network & iptables rules", docker_network_cleanup))
    else:
        typer.secho(f"No Docker network '{NETWORK_NAME}' found; skipping network cleanup.", fg=typer.colors.YELLOW)
    if token_present():
        steps.append(("Remove AGENTSITTER_TOKEN from ~/.bashrc", remove_token_from_bashrc))
    else:
        typer.secho("No AGENTSITTER_TOKEN found; skipping token cleanup.", fg=typer.colors.YELLOW)


    if not steps:
        typer.secho("Nothing to clean up.", fg=typer.colors.GREEN)
        return

    for description, action in steps:
        if typer.confirm(f"{description}?"):
            action()
        else:
            typer.secho(f"Skipped: {description}", fg=typer.colors.YELLOW)

@app.command()
def token():
    """
    Show the URL where you can obtain a new API token.
    Prompt for your API token, export it to this session and
    persist it in ~/.bashrc (avoiding duplicates).
    """
    webbrowser.open(DEFAULT_TOKEN_URL)
    typer.secho(f"Obtain your API token at: {DEFAULT_TOKEN_URL}", fg=typer.colors.BLUE)
    # prompt
    token_val = typer.prompt("Paste your AgentSitter API token")

    # set in current session
    os.environ["AGENTSITTER_TOKEN"] = token_val
    typer.secho("AGENTSITTER_TOKEN set in current session", fg=typer.colors.GREEN)

    # ensure bashrc exists
    lines = BASHRC_PATH.read_text().splitlines() if BASHRC_PATH.exists() else []
    export_line = f'export AGENTSITTER_TOKEN="{token_val}"'

    # remove any old export
    lines = [l for l in lines if not l.strip().startswith("export AGENTSITTER_TOKEN=")]
    lines.append(export_line)
    BASHRC_PATH.write_text("\n".join(lines) + "\n")
    typer.secho(f"Added AGENTSITTER_TOKEN to {BASHRC_PATH}", fg=typer.colors.GREEN)
    # 3) print the export for the parent shell
    typer.echo("to set env var run:")
    export_cmd = f'export AGENTSITTER_TOKEN="{token_val}"'
    typer.echo(export_cmd)


@app.command()
def cert_install():
    """
    Fetch and trust the AgentSitter root CA certificate:
      - Linux: import into NSS DB (~/.pki/nssdb) for Firefox/Chromium
      - macOS: add to System keychain for Safari/Chrome
    """
    # Always fetch the latest CA cert
    subprocess.run(["curl", "-sSL", CERT_URL, "-o", str(CERT_PATH)], check=True)
    typer.secho(f"Fetched CA certificate to {CERT_PATH}", fg=typer.colors.GREEN)

    if sys.platform.startswith("linux"):
        nssdb = Path.home() / ".pki" / "nssdb"
        nssdb.mkdir(parents=True, exist_ok=True)
        subprocess.run([
            "certutil", "-A", "-d", f"sql:{nssdb}",
            "-n", "agent-sitter", "-t", "C,,", "-i", str(CERT_PATH)
        ], check=True)
        typer.secho("Imported CA into NSS DB for Firefox/Chromium", fg=typer.colors.GREEN)

    elif sys.platform == "darwin":
        subprocess.run([
            "sudo", "security", "add-trusted-cert",
            "-d", "-r", "trustRoot",
            "-k", "/Library/Keychains/System.keychain",
            str(CERT_PATH)
        ], check=True)
        typer.secho("Imported CA into macOS System keychain", fg=typer.colors.GREEN)

    else:
        typer.secho("Unsupported OS for automatic cert install", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def cert_remove():
    """
    Remove the trusted CA certificate:
      - Linux: delete from NSS DB
      - macOS: delete from System keychain
    """
    if sys.platform.startswith("linux"):
        nssdb = Path.home() / ".pki" / "nssdb"
        subprocess.run([
            "certutil", "-d", f"sql:{nssdb}", "-D", "-n", "agent-sitter"
        ], check=False)
        typer.secho("Removed CA from NSS DB", fg=typer.colors.GREEN)

    elif sys.platform == "darwin":
        subprocess.run([
            "sudo", "security", "delete-certificate", "-c", "agent-sitter"
        ], check=False)
        typer.secho("Removed CA from macOS System keychain", fg=typer.colors.GREEN)

    else:
        typer.secho("Unsupported OS for automatic cert removal", fg=typer.colors.RED)
        raise typer.Exit(1)


@app.command()
def cert_ls():
    """
    List the AgentSitter CA certificates currently installed:
      - Linux: show entries in NSS DB
      - macOS: show entries in System keychain
    """
    if sys.platform.startswith("linux"):
        nssdb = Path.home() / ".pki" / "nssdb"
        typer.secho("Certificates in NSS DB (~/.pki/nssdb):", fg=typer.colors.BLUE)
        subprocess.run(["certutil", "-L", "-d", f"sql:{nssdb}"], check=False)

    elif sys.platform == "darwin":
        typer.secho("Certificates in macOS System keychain with label 'agent-sitter':", fg=typer.colors.BLUE)
        subprocess.run([
            "security", "find-certificate", "-c", "agent-sitter", "-a", "-Z"
        ], check=False)

    else:
        typer.secho("Unsupported OS for cert listing", fg=typer.colors.RED)
        raise typer.Exit(1)


def resolve_proxy_ip(host: str) -> str:
    try:
        return socket.gethostbyname(host)
    except socket.gaierror:
        typer.secho(f"ERROR: Unable to resolve proxy host '{host}'", fg=typer.colors.RED)
        raise typer.Exit(1)


def inspect_network() -> dict:
    out = subprocess.check_output([
        "docker", "network", "inspect", NETWORK_NAME, "--format", "{{json .}}"
    ]).decode()
    return json.loads(out)


def get_bridge_iface(cfg: dict) -> str:
    # Try custom bridge name
    name = cfg.get("Options", {}).get("com.docker.network.bridge.name", "")
    if name and name != "<no value>":
        return name
    # Fallback to br-<first12 of ID>
    netid = cfg.get("Id", "")
    if netid:
        return f"br-{netid[:12]}"
    return ""


@app.command()
def docker_network_setup(
    proxy_host: str = DEFAULT_PROXY_HOST,
    proxy_port: int = DEFAULT_PROXY_PORT
):
    """
    Create Docker network 'agent-sitter-net' and insert iptables rules
    to force containers to use the proxy.
    """
    proxy_ip = resolve_proxy_ip(proxy_host)

    # 1. Create network if missing
    exists = subprocess.run(
        ["docker", "network", "inspect", NETWORK_NAME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0
    if not exists:
        typer.secho(f"Creating Docker network '{NETWORK_NAME}'...", fg=typer.colors.GREEN)
        subprocess.run(["docker", "network", "create", "--driver", "bridge", NETWORK_NAME], check=True)
    else:
        typer.secho(f"Network '{NETWORK_NAME}' already exists; skipping creation.", fg=typer.colors.YELLOW)

    # 2. Inspect network for subnet and gateway
    cfg = inspect_network()
    ipam = cfg.get("IPAM", {}).get("Config", [{}])[0]
    subnet = ipam.get("Subnet", "")
    gateway = ipam.get("Gateway", "")
    typer.echo(f"Subnet: {subnet}")
    typer.echo(f"Gateway: {gateway}")

    # 3. Determine bridge interface
    bridge = get_bridge_iface(cfg)
    if not bridge:
        typer.secho("ERROR: Could not determine bridge interface.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.echo(f"Bridge interface: {bridge}")

    # 4. Insert iptables rules in DOCKER-USER
    typer.secho("Inserting iptables rules...", fg=typer.colors.BLUE)
    rules = [
        ["sudo", "iptables", "-I", "DOCKER-USER", "1", "-i", bridge, "-p", "udp", "--dport", "53", "-j", "ACCEPT"],
        ["sudo", "iptables", "-I", "DOCKER-USER", "1", "-i", bridge, "-p", "tcp", "--dport", "53", "-j", "ACCEPT"],
        ["sudo", "iptables", "-I", "DOCKER-USER", "1", "-i", bridge, "-p", "tcp", "-d", proxy_ip, "--dport", str(proxy_port), "-j", "ACCEPT"],
        ["sudo", "iptables", "-I", "DOCKER-USER", "1", "-i", bridge, "-j", "DROP"],
    ]
    for rule in rules:
        subprocess.run(rule, check=True)

    # 5. Show current rules
    typer.echo()
    subprocess.run(["sudo", "iptables", "-L", "DOCKER-USER", "-n", "--line-numbers"], check=False)


@app.command()
def docker_network_cleanup(
    proxy_host: str = DEFAULT_PROXY_HOST,
    proxy_port: int = DEFAULT_PROXY_PORT
):
    """
    Remove iptables rules and delete Docker network 'agent-sitter-net'.
    """
    proxy_ip = resolve_proxy_ip(proxy_host)

    # 1. Try to get bridge iface (if network exists)
    try:
        cfg = inspect_network()
        bridge = get_bridge_iface(cfg)
        typer.echo(f"Detected bridge interface: {bridge}")
    except subprocess.CalledProcessError:
        bridge = ""
        typer.secho("Network not found; skipping iptables cleanup.", fg=typer.colors.YELLOW)

    # 2. Remove iptables rules
    if bridge:
        typer.secho("Removing iptables rules...", fg=typer.colors.BLUE)
        delete_cmds = [
            ["sudo", "iptables", "-D", "DOCKER-USER", "-i", bridge, "-p", "udp", "--dport", "53", "-j", "ACCEPT"],
            ["sudo", "iptables", "-D", "DOCKER-USER", "-i", bridge, "-p", "tcp", "--dport", "53", "-j", "ACCEPT"],
            ["sudo", "iptables", "-D", "DOCKER-USER", "-i", bridge, "-p", "tcp", "-d", proxy_ip, "--dport", str(proxy_port), "-j", "ACCEPT"],
            ["sudo", "iptables", "-D", "DOCKER-USER", "-i", bridge, "-j", "DROP"],
        ]
        for cmd in delete_cmds:
            subprocess.run(cmd, check=False)

    # 3. Remove Docker network
    removed = subprocess.run(
        ["docker", "network", "rm", NETWORK_NAME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    ).returncode == 0
    if removed:
        typer.secho(f"Removed Docker network '{NETWORK_NAME}'", fg=typer.colors.GREEN)
    else:
        typer.secho(f"No Docker network '{NETWORK_NAME}' to remove", fg=typer.colors.YELLOW)


def ensure_stunnel_installed():
    """
    Ensure 'stunnel' is installed, attempting apt-get or brew if missing.
    """
    if shutil.which("stunnel"):
        return
    typer.secho("stunnel not found—installing...", fg=typer.colors.YELLOW)
    if shutil.which("apt-get"):
        subprocess.run(["sudo", "apt-get", "update"], check=False)
        subprocess.run(["sudo", "apt-get", "install", "-y", "stunnel4"], check=True)
    elif shutil.which("brew"):
        subprocess.run(["brew", "install", "stunnel"], check=True)
    else:
        typer.secho("Could not auto-install stunnel; please install manually.", fg=typer.colors.RED)
        raise typer.Exit(1)
    typer.secho("stunnel installed successfully.", fg=typer.colors.GREEN)


@app.command()
def tunnel_start():
    """
    Start an stunnel to the AgentSitter proxy.
    """
    ensure_stunnel_installed()
    conf = [
        "foreground = no",
        "[proxy]",
        "client = yes",
        f"accept = {DEFAULT_PROXY_HOST}:{DEFAULT_PROXY_PORT}"
    ]
    try:
        cfg = inspect_network()
        bridge = get_bridge_iface(cfg)
        gw = cfg.get("IPAM", {}).get("Config", [{}])[0].get("Gateway", "")
        if gw:
            conf.append(f"accept = {gw}:{DEFAULT_PROXY_PORT}")
            typer.secho(f"Also binding on Docker bridge at {gw}:{DEFAULT_PROXY_PORT}", fg=typer.colors.GREEN)
    except Exception:
        typer.secho("No Docker bridge bind (network not found).", fg=typer.colors.YELLOW)

    conf.append("connect = sitter.agentsitter.ai:3128")
    proc = subprocess.Popen(["stunnel", "-fd", "0"], stdin=subprocess.PIPE)
    proc.communicate(input="\n".join(conf).encode())
    typer.secho("Stunnel started.", fg=typer.colors.GREEN)


@app.command()
def tunnel_stop():
    """
    Stop any running stunnel process.
    """
    subprocess.run(["pkill", "stunnel"], check=False)
    typer.secho("Stopped stunnel.", fg=typer.colors.GREEN)


@app.command()
def dashboard():
    """
    Open the live AgentSitter dashboard in your default browser.
    """
    webbrowser.open(DEFAULT_DASHBOARD_URL)
    typer.secho(f"Opened dashboard at {DEFAULT_DASHBOARD_URL}", fg=typer.colors.GREEN)

@app.command()
def status():
    """
    Show sittr health:
      • tunnel up?
      • cert trusted?
      • docker network exists?
    """
    # 1. Is stunnel running?
    try:
        tunnel_up = tunnel_running()
    except Exception:
        tunnel_up = False
    typer.secho(f"Tunel started: {'✅' if tunnel_up else '❌'}")
        
    # 2. Is our CA cert installed?
    try:
        cert_ok = cert_installed()
    except Exception:
        cert_ok = False
    typer.secho(f"CA certificate trusted: {'✅' if cert_ok else '❌'}")

    # 3. Is the Docker network present?
    try:
        net_ok = network_exists()
    except Exception:
        net_ok = False
    typer.secho(f"Docker network '{NETWORK_NAME}' exists: {'✅' if net_ok else '❌'}")

    # 4) API token configured in bashrc?
    token_ok = token_present()
    typer.secho(f"API token configured in bashrc: {'✅' if token_ok else '❌'}")


if __name__ == "__main__":
    app()
