import os
import json
import time
from typing import Optional, Any
from openai import OpenAI


class LLMClient:
    """统一的 LLM 调用封装。所有技能和编排器通过它调用模型。"""

    def __init__(self, config: Optional[dict] = None):
        cfg = config or {}
        self.api_key = cfg.get("api_key") or os.getenv("LLM_API_KEY")
        self.base_url = cfg.get("base_url") or os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
        self.model = cfg.get("model") or os.getenv("LLM_MODEL", "deepseek-flash")
        self.max_retries = cfg.get("max_retries", 3)
        self.timeout = cfg.get("timeout", 60)
        self.thinking = cfg.get("thinking", False)

        if not self.api_key:
            raise ValueError("LLM_API_KEY is not set")

        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.total_tokens = 0

    def chat(self, system: str, user: str, temperature: float = 0.3) -> str:
        """发送一次对话请求，返回文本。失败时自动重试。"""
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        extra = {}
        if not self.thinking:
            extra["extra_body"] = {"thinking": {"type": "disabled"}}

        last_error = None
        for attempt in range(self.max_retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    timeout=self.timeout,
                    **extra,
                )
                usage = resp.usage
                if usage:
                    self.total_tokens += usage.total_tokens
                content = resp.choices[0].message.content
                return content or ""
            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    time.sleep(2 ** attempt)
                continue

        raise RuntimeError(f"LLM call failed after {self.max_retries} retries: {last_error}")

    def chat_json(self, system: str, user: str, temperature: float = 0.3) -> Any:
        """发送请求，要求模型返回 JSON，解析后返回对象。"""
        system_with_json = system + "\n\n必须只输出合法的 JSON，不要包含任何解释或 Markdown 代码块标记。"
        raw = self.chat(system_with_json, user, temperature)
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[-1]
            if raw.endswith("```"):
                raw = raw[:-3]
            raw = raw.strip()
        return json.loads(raw)

    def stats(self) -> dict:
        return {"total_tokens": self.total_tokens}