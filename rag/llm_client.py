import os
import requests
from typing import Optional


class OllamaClient:
    """
    本地 Ollama 大模型客户端
    负责普通文本生成和原生工具调用。
    """
    def __init__(
        self,
        model_name: str = "qwen2.5:7b",
        base_url: str | None = None,
    ):
        self.model_name = model_name
        self.base_url = (
            base_url
            or os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        ).rstrip("/")
        self.generate_url = f"{self.base_url}/api/generate"
        self.chat_url = f"{self.base_url}/api/chat"

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
    ) -> str:
        """普通文本生成。"""

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
        }

        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(
                self.generate_url,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()
            return response.json().get("response", "")

        except requests.exceptions.RequestException as e:
            print(f"[OllamaClient] 请求失败: {e}")
            return ""

    def chat(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """
        多轮对话，支持 Ollama 原生工具调用。

        返回模型的完整 message，包含 content 和 tool_calls。
        """

        payload = {
            "model": self.model_name,
            "messages": messages,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools

        try:
            response = requests.post(
                self.chat_url,
                json=payload,
                timeout=120,
            )
            response.raise_for_status()

            data = response.json()
            message = data.get("message")

            if not isinstance(message, dict):
                raise ValueError("Ollama 返回的 message 格式不正确")

            return message

        except requests.exceptions.RequestException as e:
            print(f"[OllamaClient] Chat 请求失败: {e}")
            raise

    def chat_text(
        self,
        messages: list[dict],
    ) -> str:
        """普通多轮对话，只返回文本内容。"""

        message = self.chat(messages)
        return message.get("content", "")


# 实例化一个全局客户端
ollama_client = OllamaClient()


if __name__ == "__main__":
    reply = ollama_client.generate(
        "你好，请用一句话介绍你自己"
    )
    print(f"模型回复: {reply}")
