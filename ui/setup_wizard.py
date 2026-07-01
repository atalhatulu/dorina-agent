"""Setup wizard — first-run configuration for API keys, model, and preferences."""
from __future__ import annotations
import json
from pathlib import Path
from core.constants import DORINA_HOME
from rich.console import Console
from rich.prompt import Prompt, Confirm
from rich.panel import Panel
from rich import box
from providers.keys import PROVIDERS as PROVIDER_CONFIG

console = Console()

# Backward compatibility: old provider names → canonical keys.py names
PROVIDER_ALIASES = {
    "google": "gemini",
}

# Provider models for the setup wizard — derives from canonical config
PROVIDER_MODELS = {
    name: info['models']
    for name, info in PROVIDER_CONFIG.items()
}

PROVIDERS = [("google", "Google Gemini", True)]


def _resolve_provider(name: str) -> str:
    """Resolve provider name (with backward compat aliases)."""
    return PROVIDER_ALIASES.get(name, name)


async def run_setup_wizard():
    """Interactive setup wizard."""
    console.print(Panel.fit(
        "[bold #D4622A]Dorina Agent Setup[/bold #D4622A]\n\n"
        "Configure your agent. All settings saved to ~/.dorina/",
        border_style="#D4622A",
    ))

    config = {}

    # Step 1: Select Provider
    console.print("\n[bold]Step 1: Select Provider[/bold]")
    from ui.provider_selector import select_provider
    from providers.keys import keys as km

    provider = await select_provider(_resolve_provider(config.get("provider", "")))
    if provider is None:
        console.print("  [yellow]Cancelled[/yellow]")
        return config

    needs_key = next((p[2] for p in PROVIDERS if p[0] == provider), True)
    config["provider"] = provider
    console.print(f"  [green]Selected: {provider}[/green]")

    # Step 2: API Key
    if needs_key:
        existing = km.get_key(provider)
        if existing:
            action = Prompt.ask(
                f"  Key for [bold]{provider}[/bold] exists.",
                choices=["k", "c", "r"],
                default="k",
            )
            if action.lower() in ("c", "r"):
                existing = ""

        if not existing:
            models = PROVIDER_MODELS.get(provider, [])
            console.print(f"\n  Available models for [bold]{provider}[/bold]:")
            for m in models:
                console.print(f"    \u2022 {m}")
            key = Prompt.ask(f"\n  Enter your {provider} API key", password=True)
            if key:
                km.save_key(provider, key)
                console.print(f"  [green]Key saved[/green]")

                # Model selection
                console.print(f"\n  Select model for [bold]{provider}[/bold]:")
                for i, m in enumerate(models, 1):
                    console.print(f"    {i}) {m}")
                mc = Prompt.ask(
                    "  Number",
                    choices=[str(i) for i in range(1, len(models) + 1)] + ["d"],
                    default="1",
                )
                if mc.lower() != "d":
                    config["model"] = f"{provider}/{models[int(mc) - 1]}"
                else:
                    config["model"] = f"{provider}/{models[0]}"

    # Step 3: Model fallback
    if "model" not in config:
        m = Prompt.ask("  Model name", default="deepseek/deepseek-v4-flash")
        config["model"] = m

    # Step 4: Preferences
    config["language"] = Prompt.ask("  Language (tr/en)", default="tr")
    config["status_bar"] = Confirm.ask("  Show status bar?", default=True)

    # Save both to setup.json AND config.yaml
    config_dir = DORINA_HOME
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "setup.json").write_text(json.dumps(config, indent=2))
    
    # Update ~/.dorina/config.yaml with new model/provider
    yaml_path = config_dir / "config.yaml"
    try:
        import yaml
        if yaml_path.exists():
            yaml_data = yaml.safe_load(yaml_path.read_text()) or {}
        else:
            yaml_data = {}
        if "model" in config:
            yaml_data.setdefault("model", {})["default"] = config["model"]
        if "provider" in config:
            yaml_data.setdefault("model", {})["provider"] = config["provider"]
        yaml_path.write_text(yaml.dump(yaml_data, default_flow_style=False, allow_unicode=True))
        console.print(f"  [green]Config.yaml guncellendi[/green]")
    except ImportError:
        console.print("  [dim]pyyaml kurulu degil, config.yaml guncellenemedi[/dim]")
    except Exception as e:
        console.print(f"  [dim]Config.yaml guncellenemedi: {e}[/dim]")

    console.print(Panel.fit(
        "[bold green]Setup complete![/bold green]\n"
        f"  Model: {config.get('model', 'default')}\n"
        f"  Language: {config['language']}\n\n"
        "[dim]Type /setup to reconfigure.[/dim]",
        border_style="green",
    ))
    return config


def needs_setup() -> bool:
    return not (DORINA_HOME / "setup.json").exists()


def run_user_profile_wizard() -> dict:
    """Kullanici profili wizardi. Bilgiler ~/.dorina/user_profile.json'a kaydedilir."""
    console.print(Panel.fit(
        "[bold #D4622A]Dorina - Ilk Kurulum[/bold #D4622A]\\n\\n"
        "Bir kere soruyorum, sonra bir daha sormam.\\n"
        "Bilgiler ~/.dorina/user_profile.json'a kaydedilir.",
        border_style="#D4622A",
    ))
    
    profile = {}
    profile["name"] = Prompt.ask("  Adin", default="Kullanici")
    profile["profession"] = Prompt.ask("  Meslek / kullanim alani", default="Gelistirici")
    
    age = Prompt.ask("  Yas (opsiyonel)", default="")
    if age and age.isdigit():
        profile["age"] = int(age)
    
    # Isleim sistemini otomatik tespit et
    import platform as _p
    _os_str = f"{_p.system()} {_p.release()}"
    os_confirm = Confirm.ask(f"  Isleim sistemi: [bold]{_os_str}[/bold]", default=True)
    if os_confirm:
        profile["os"] = _os_str
    else:
        profile["os"] = Prompt.ask("  Isleim sistemin")
    
    lang = Prompt.ask("  Tercih dili", choices=["tr", "en"], default="tr")
    profile["language"] = lang
    
    default_dir = str(Path.cwd())
    proj_dir = Prompt.ask(f"  Ana proje dizini", default=default_dir)
    profile["project_dir"] = proj_dir if proj_dir else default_dir
    
    editor = Prompt.ask("  Editor / IDE (opsiyonel)", default="")
    if editor:
        profile["editor"] = editor
    
    # Kisiselik secimi
    personality = Prompt.ask(
        "  Dorina'nin konusma stili",
        choices=["p", "d", "a"],
        default="d",
    )
    style_map = {"p": "professional", "d": "dengeli", "a": "arkadas"}
    profile["personality_style"] = style_map.get(personality, "dengeli")
    
    config_dir = DORINA_HOME
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "user_profile.json").write_text(
        json.dumps(profile, indent=2, ensure_ascii=False)
    )
    
    console.print(f"  [green]Profil kaydedildi! Hos geldin {profile['name']}![/green]")
    return profile


def has_user_profile() -> bool:
    """Kullanici profili var mi?"""
    return (DORINA_HOME / "user_profile.json").exists()
