'''API Key Manager — supports all providers, auto-detects from env.'''
import os
import json
from pathlib import Path

PROVIDERS = {
    'deepseek': {'env': 'DEEPSEEK_API_KEY', 'url': 'https://api.deepseek.com', 'models': ['deepseek-chat', 'deepseek-v4-flash']},
    'groq': {'env': 'GROQ_API_KEY', 'url': 'https://api.groq.com/openai/v1', 'models': ['llama-3.3-70b-versatile', 'llama-3.1-8b-instant', 'qwen/qwen3-32b']},
    'openrouter': {'env': 'OPENROUTER_API_KEY', 'url': 'https://openrouter.ai/api/v1', 'models': ['openai/gpt-4o-mini', 'openrouter/free', 'google/gemma-4-31b-it', 'qwen/qwen3-next-80b-a3b-instruct']},
    'openai': {'env': 'OPENAI_API_KEY', 'url': 'https://api.openai.com/v1', 'models': ['gpt-4o-mini', 'gpt-4o']},
    'anthropic': {'env': 'ANTHROPIC_API_KEY', 'url': 'https://api.anthropic.com/v1', 'models': ['claude-sonnet-4']},
    'google': {'env': 'GOOGLE_API_KEY', 'url': 'https://generativelanguage.googleapis.com/v1beta', 'models': ['gemini-2.5-pro']},
    'mistral': {'env': 'MISTRAL_API_KEY', 'url': 'https://api.mistral.ai/v1', 'models': ['mistral-large-latest', 'mistral-small-latest', 'open-mistral-nemo']},
    'xai': {'env': 'XAI_API_KEY', 'url': 'https://api.x.ai/v1', 'models': ['grok-2-latest']},
    'cohere': {'env': 'COHERE_API_KEY', 'url': 'https://api.cohere.com/v1', 'models': ['command-r-plus', 'command-r']},
    'perplexity': {'env': 'PERPLEXITY_API_KEY', 'url': 'https://api.perplexity.ai', 'models': ['sonar-pro', 'sonar']},
    'fireworks': {'env': 'FIREWORKS_API_KEY', 'url': 'https://api.fireworks.ai/inference/v1', 'models': ['accounts/fireworks/models/llama-v3p3-70b-instruct']},
    'replicate': {'env': 'REPLICATE_API_KEY', 'url': 'https://api.replicate.com/v1', 'models': ['meta/meta-llama-3-70b-instruct']},
    'siliconflow': {'env': 'SILICONFLOW_API_KEY', 'url': 'https://api.siliconflow.cn/v1', 'models': ['deepseek-ai/DeepSeek-V3']},
    'together': {'env': 'TOGETHER_API_KEY', 'url': 'https://api.together.xyz/v1', 'models': ['mistralai/Mixtral-8x7B-Instruct-v0.1']},
    'ollama': {'env': '', 'url': 'http://localhost:11434', 'models': ['llama3', 'mistral']},
    'huggingface': {'env': 'HF_API_KEY', 'url': 'https://api-inference.huggingface.co/v1', 'models': ['meta-llama/Llama-3.3-70B-Instruct', 'microsoft/Phi-3.5-mini-instruct']},
    'deepinfra': {'env': 'DEEPINFRA_API_KEY', 'url': 'https://api.deepinfra.com/v1/openai', 'models': ['meta-llama/Llama-3.3-70B-Instruct-Turbo', 'Qwen/Qwen3-30B-A3B']},
    'nvidia': {'env': 'NVIDIA_API_KEY', 'url': 'https://integrate.api.nvidia.com/v1', 'models': ['nvidia/llama-3.3-nemotron-super-49b-v1']},
    'azure': {'env': 'AZURE_OPENAI_API_KEY', 'url': 'https://YOUR_RESOURCE.openai.azure.com', 'models': ['gpt-4o-mini', 'gpt-4o']},
    'bedrock': {'env': 'AWS_ACCESS_KEY_ID', 'url': 'https://bedrock-runtime.us-east-1.amazonaws.com', 'models': ['anthropic.claude-sonnet-4']},
    'minimax': {'env': 'MINIMAX_API_KEY', 'url': 'https://api.minimax.chat/v1', 'models': ['MiniMax-Text-01']},
    'qwen': {'env': 'QWEN_API_KEY', 'url': 'https://dashscope.aliyuncs.com/compatible-mode/v1', 'models': ['qwen3-30b-a3b', 'qwen-turbo-latest']},
    'novita': {'env': 'NOVITA_API_KEY', 'url': 'https://api.novita.ai/v3/openai', 'models': ['meta-llama/llama-3.3-70b-instruct']},
}

class KeyManager:
    def __init__(self):
        self._keys = {}
        self._load_from_env()
        self._load_from_file()
    
    def _load_from_env(self):
        for name, info in PROVIDERS.items():
            env_key = info['env']
            if env_key and os.getenv(env_key):
                self._keys[name] = os.getenv(env_key)
    
    def _load_from_file(self):
        key_file = Path.home() / '.dorina' / 'keys.json'
        if key_file.exists():
            try:
                data = json.loads(key_file.read_text())
                self._keys.update(data)
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
