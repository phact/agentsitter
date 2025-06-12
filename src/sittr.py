#!/usr/bin/env python3
"""
sittr CLI tool for AgentSitter.ai
"""
import sys
import subprocess
import webbrowser
import shutil
import typer
from pathlib import Path

app = typer.Typer(help="AgentSitter.ai CLI (sittr)")

DEFAULT_PROXY_HOST = "localhost"
DEFAULT_PROXY_PORT = 8080
DEFAULT_DASHBOARD_URL = "https://agentsitter.ai"
CERT_URL = "https://agentsitter.ai/certs/ca-cert.pem"
CERT_PATH = Path.cwd() / "ca-cert.pem"

@app.callback(invoke_without_command=True, help="Show help when no command is provided.")
def main(ctx: typer.Context):
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()

@app.command()
def token():
    """
    Show the URL where you can obtain a new API token.
    """
    typer.echo("Obtain your API token at:")
    typer.secho("https://www.agentsitter.ai/token/new", fg=typer.colors.BLUE)

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
        subprocess.run([
            "certutil", "-L", "-d", f"sql:{nssdb}"
        ], check=False)

    elif sys.platform == "darwin":
        typer.secho("Certificates in macOS System keychain with label 'agent-sitter':", fg=typer.colors.BLUE)
        subprocess.run([
            "security", "find-certificate", "-c", "agent-sitter", "-a", "-Z"
        ], check=False)

    else:
        typer.secho("Unsupported OS for cert listing", fg=typer.colors.RED)
        raise typer.Exit(1)

@app.command()
def network_setup(
    proxy_host: str = DEFAULT_PROXY_HOST,
    proxy_port: int = DEFAULT_PROXY_PORT
):
    """
    Create Docker network 'agent-sitter-net' and insert iptables rules
    to force containers to use the proxy.
    """
    script = Path(__file__).parent / "agent-network-manager.sh"
    subprocess.run(["sudo", str(script), "setup", proxy_host, str(proxy_port)], check=True)
    typer.secho("Docker network setup complete.", fg=typer.colors.GREEN)

@app.command()
def network_cleanup(
    proxy_host: str = DEFAULT_PROXY_HOST,
    proxy_port: int = DEFAULT_PROXY_PORT
):
    """
    Remove iptables rules and delete the Docker network.
    """
    script = Path(__file__).parent / "agent-network-manager.sh"
    subprocess.run(["sudo", str(script), "cleanup", proxy_host, str(proxy_port)], check=True)
    typer.secho("Docker network cleanup complete.", fg=typer.colors.GREEN)

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
    Start an stunnel to the AgentSitter proxy:
      • binds on 127.0.0.1:8080
      • also binds on Docker bridge gateway if 'agent-sitter-net' exists
    """
    ensure_stunnel_installed()
    conf = [
        "foreground = no",
        "[proxy]",
        "client = yes",
        f"accept = {DEFAULT_PROXY_HOST}:{DEFAULT_PROXY_PORT}"
    ]
    try:
        gw = subprocess.check_output([
            "docker","network","inspect","agent-sitter-net",
            "--format","{{(index .IPAM.Config 0).Gateway}}"
        ]).decode().strip()
        if gw:
            conf.append(f"accept = {gw}:{DEFAULT_PROXY_PORT}")
            typer.secho(f"Also binding on Docker bridge at {gw}:{DEFAULT_PROXY_PORT}", fg=typer.colors.GREEN)
    except subprocess.CalledProcessError:
        typer.secho("No Docker bridge bind (network not found).", fg=typer.colors.YELLOW)
    conf.append("connect = sitter.agentsitter.ai:3128")
    proc = subprocess.Popen(["stunnel","-fd","0"], stdin=subprocess.PIPE)
    proc.communicate(input="\n".join(conf).encode())
    typer.secho("Stunnel started.", fg=typer.colors.GREEN)

@app.command()
def tunnel_stop():
    """
    Stop any running stunnel process.
    """
    subprocess.run(["pkill","stunnel"], check=False)
    typer.secho("Stopped stunnel.", fg=typer.colors.GREEN)

@app.command()
def dashboard():
    """
    Open the live AgentSitter dashboard in your default browser.
    """
    webbrowser.open(DEFAULT_DASHBOARD_URL)
    typer.secho(f"Opened dashboard at {DEFAULT_DASHBOARD_URL}", fg=typer.colors.GREEN)

@app.command()
def proxy_enable():
    """
    Enable system/browser proxy to localhost:8080.
    """
    if sys.platform == "darwin":
        services = subprocess.check_output(["networksetup","-listallnetworkservices"]).decode().splitlines()[1:]
        for svc in services:
            subprocess.run(["networksetup","-setwebproxy",svc,DEFAULT_PROXY_HOST,str(DEFAULT_PROXY_PORT)], check=False)
            subprocess.run(["networksetup","-setsecurewebproxy",svc,DEFAULT_PROXY_HOST,str(DEFAULT_PROXY_PORT)], check=False)
        typer.secho("Proxy enabled on all macOS network services.", fg=typer.colors.GREEN)
    else:
        typer.secho(f"Proxy enabled at http://{DEFAULT_PROXY_HOST}:{DEFAULT_PROXY_PORT}", fg=typer.colors.GREEN)

@app.command()
def status():
    """
    Show a brief sittr status summary.
    """
    typer.echo(f"Proxy: {DEFAULT_PROXY_HOST}:{DEFAULT_PROXY_PORT}")
    typer.echo(f"Dashboard: {DEFAULT_DASHBOARD_URL}")

if __name__ == "__main__":
    app()

