'''API Key Manager — supports all providers, auto-detects from env and secrets.yaml.'''
import os
import json
from pathlib import Path

SECRETS_FILE = Path.home() / '.dorina' / 'secrets.yaml'

PROVIDERS = {
    'deepseek': {'env': 'DEEPSEEK_API_KEY', 'url': 'https://api.deepseek.com', 'models': ['deepseek-chat', 'deepseek-v4-flash'], 'display': 'DeepSeek (V3, R1, coder, direct API)', 'needs_key': True},
    'groq': {'env': 'GROQ_API_KEY', 'url': 'https://api.groq.com/openai/v1', 'models': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'qwen/qwen3-32b'], 'display': 'Groq (Free tier, very fast inference)', 'needs_key': True},
    'openrouter': {'env': 'OPENROUTER_API_KEY', 'url': 'https://openrouter.ai/api/v1', 'models': ['openai/gpt-4o-mini', 'openrouter/free', 'google/gemma-4-31b-it', 'qwen/qwen3-next-80b-a3b-instruct'], 'display': 'OpenRouter (Pay-per-use API aggregator, 200+ models)', 'needs_key': True},
    'openai': {'env': 'OPENAI_API_KEY', 'url': 'https://api.openai.com/v1', 'models': ['gpt-4o-mini', 'gpt-4o'], 'display': 'OpenAI (GPT-4o, GPT-4.1, Codex CLI)', 'needs_key': True},
    'anthropic': {'env': 'ANTHROPIC_API_KEY', 'url': 'https://api.anthropic.com/v1', 'models': ['claude-sonnet-4'], 'display': 'Anthropic (Claude models via API)', 'needs_key': True},
    'gemini': {'env': 'GOOGLE_API_KEY', 'url': 'https://generativelanguage.googleapis.com/v1beta', 'models': ['gemini-2.0-flash', 'gemini-2.5-pro'], 'display': 'Google AI Studio (Native Gemini API)', 'needs_key': True},
    'mistral': {'env': 'MISTRAL_API_KEY', 'url': 'https://api.mistral.ai/v1', 'models': ['mistral-large-latest', 'mistral-small-latest', 'open-mistral-nemo'], 'display': 'Mistral AI (Mistral Large, Small)', 'needs_key': True},
    'xai': {'env': 'XAI_API_KEY', 'url': 'https://api.x.ai/v1', 'models': ['grok-2-latest'], 'display': 'xAI (Grok models)', 'needs_key': True},
    'cohere': {'env': 'COHERE_API_KEY', 'url': 'https://api.cohere.com/v1', 'models': ['command-r-plus', 'command-r'], 'display': 'Cohere (Command R models)', 'needs_key': True},
    'perplexity': {'env': 'PERPLEXITY_API_KEY', 'url': 'https://api.perplexity.ai', 'models': ['sonar-pro', 'sonar'], 'display': 'Perplexity (Sonar models)', 'needs_key': True},
    'fireworks': {'env': 'FIREWORKS_API_KEY', 'url': 'https://api.fireworks.ai/inference/v1', 'models': ['accounts/fireworks/models/llama-v3p3-70b-instruct'], 'display': 'Fireworks AI (Fast inference)', 'needs_key': True},
    'replicate': {'env': 'REPLICATE_API_KEY', 'url': 'https://api.replicate.com/v1', 'models': ['meta/meta-llama-3-70b-instruct'], 'display': 'Replicate (Open-source model hosting)', 'needs_key': True},
    'siliconflow': {'env': 'SILICONFLOW_API_KEY', 'url': 'https://api.siliconflow.cn/v1', 'models': ['deepseek-ai/DeepSeek-V3'], 'display': 'SiliconFlow (China, free tier, DeepSeek models)', 'needs_key': True},
    'together': {'env': 'TOGETHER_API_KEY', 'url': 'https://api.together.xyz/v1', 'models': ['mistralai/Mixtral-8x7B-Instruct-v0.1'], 'display': 'Together AI (Open-source model hosting)', 'needs_key': True},
    'ollama': {'env': '', 'url': 'http://localhost:11434', 'models': ['llama3', 'mistral'], 'display': 'Ollama (Local, 127.0.0.1:11434, no key needed)', 'needs_key': False},
    'huggingface': {'env': 'HF_API_KEY', 'url': 'https://api-inference.huggingface.co/v1', 'models': ['meta-llama/Llama-3.3-70B-Instruct', 'microsoft/Phi-3.5-mini-instruct'], 'display': 'HuggingFace Inference API', 'needs_key': True},
    'deepinfra': {'env': 'DEEPINFRA_API_KEY', 'url': 'https://api.deepinfra.com/v1/openai', 'models': ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'Qwen/Qwen3-30B-A3B'], 'display': 'DeepInfra (Serverless inference)', 'needs_key': True},
    'nvidia': {'env': 'NVIDIA_API_KEY', 'url': 'https://integrate.api.nvidia.com/v1', 'models': ['nvidia/llama-3.3-nemotron-super-49b-v1'], 'display': 'NVIDIA NIM (GPU-accelerated)', 'needs_key': True},
    'azure': {'env': 'AZURE_OPENAI_API_KEY', 'url': 'https://YOUR_RESOURCE.openai.azure.com', 'models': ['gpt-4o-mini', 'gpt-4o'], 'display': 'Azure OpenAI (Enterprise)', 'needs_key': True},
    'bedrock': {'env': 'AWS_ACCESS_KEY_ID', 'url': 'https://bedrock-runtime.us-east-1.amazonaws.com', 'models': ['anthropic.claude-sonnet-4'], 'display': 'AWS Bedrock (Enterprise)', 'needs_key': True},
    'minimax': {'env': 'MINIMAX_API_KEY', 'url': 'https://api.minimax.chat/v1', 'models': ['MiniMax-Text-01'], 'display': 'MiniMax (Hailuo AI)', 'needs_key': True},
    'qwen': {'env': 'QWEN_API_KEY', 'url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'models': ['qwen3-30b-a3b', 'qwen-turbo-latest'], 'display': 'Qwen (Alibaba Cloud models)', 'needs_key': True},
    'novita': {'env': 'NOVITA_API_KEY', 'url': 'https://api.novita.ai/v3/openai', 'models': ['meta-llama/llama-3.3-70b-instruct'], 'display': 'Novita AI (LLM inference)', 'needs_key': True},
}

# UI-friendly display list derived from canonical PROVIDERS config
PROVIDER_DISPLAY_LIST = [
    (name, info['display'])
    for name, info in PROVIDERS.items()
]

# Display list with needs_key flag (for setup wizard)
PROVIDER_SETUP_LIST = [
    (name, info['display'], info.get('needs_key', True))
    for name, info in PROVIDERS.items()
]

class KeyManager:
    def __init__(self):
        self._keys = {}
        # Priority: .env > specific env var > DORINA_API_KEY env var > secrets.yaml > keys.json
        self._load_dotenv()
        self._load_from_env()
        self._load_dorina_api_key_fallback()
        self._load_from_secrets_yaml()
        self._load_from_file()
    
    def _load_dotenv(self):
        """Load .env file if python-dotenv is available (optional dependency)."""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            # Try manual .env parsing as fallback
            dotenv_path = Path.cwd() / '.env'
            if not dotenv_path.exists():
                dotenv_path = Path.home() / '.dorina' / '.env'
            if dotenv_path.exists():
                for line in dotenv_path.read_text().splitlines():
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    # Remove surrounding quotes
                    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
                        value = value[1:-1]
                    if key and value and not os.getenv(key):  # Don't override existing env
                        os.environ[key] = value

    def _load_from_env(self):
        for name, info in PROVIDERS.items():
            env_key = info['env']
            if env_key and os.getenv(env_key):
                self._keys[name] = os.getenv(env_key)
    
    def _load_dorina_api_key_fallback(self):
        """If DORINA_API_KEY is set, apply it to any provider that still has no key."""
        dorina_key = os.getenv('DORINA_API_KEY')
        if not dorina_key:
            return
        for name, info in PROVIDERS.items():
            if info.get('needs_key', True) and name not in self._keys:
                self._keys[name] = dorina_key

    def _load_from_secrets_yaml(self):
        """Read keys from ~/.dorina/secrets.yaml — lower priority than env vars, higher than keys.json."""
        if not SECRETS_FILE.exists():
            return
        try:
            import yaml
            data = yaml.safe_load(SECRETS_FILE.read_text())
            if not data or not isinstance(data, dict):
                return
            # Map flat keys like 'api_key' to the first 'needs_key' provider without a key
            api_key = data.get('api_key')
            if api_key:
                for name, info in PROVIDERS.items():
                    if info.get('needs_key', True) and name not in self._keys:
                        self._keys[name] = api_key
                        break  # Assign to first unmatched provider
            # Also try per-provider keys (e.g. deepseek: sk-..., openai: sk-...)
            for name, info in PROVIDERS.items():
                if name not in self._keys and name in data:
                    self._keys[name] = data[name]
                env_key = info.get('env', '').lower().replace('_api_key', '')
                if name not in self._keys and env_key and env_key in data:
                    self._keys[name] = data[env_key]
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"secrets.yaml okunamadi: {e}")

    def _load_from_file(self):
        key_file = Path.home() / '.dorina' / 'keys.json'
        if key_file.exists():
            try:
                data = json.loads(key_file.read_text())
                # keys.json has lowest priority — only set keys not already configured
                for k, v in data.items():
                    if k not in self._keys:
                        self._keys[k] = v
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"keys.json okunamadi: {e}")

    def save_key(self, provider: str, key: str):
        self._keys[provider] = key
        key_file = Path.home() / '.dorina' / 'keys.json'
        key_file.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if key_file.exists():
            try:
                existing = json.loads(key_file.read_text())
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"keys.json bozuk, sifirlaniyor: {e}")
        existing[provider] = key
        # Atomic write: temp file + rename
        tmp = key_file.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(existing, indent=2))
        tmp.replace(key_file)
        os.environ[f"{provider.upper()}_API_KEY"] = key
    
    def get_key(self, provider: str) -> str:
        return self._keys.get(provider, '')
    
    def list_available(self) -> list[dict]:
        result = []
        for name, info in PROVIDERS.items():
            has_key = bool(self._keys.get(name))
            result.append({
                'name': name,
                'configured': has_key,
                'models': info['models'][:3],
                'url': info['url'],
            })
        return result
    
    def has_key(self, provider: str) -> bool:
        return bool(self._keys.get(provider))

keys = KeyManager()
