import requests
from typing import Optional

class OllamaClient:
    """
    本地 Ollama 大模型客户端
    负责与大模型进行对话交互
    """

    def __init__(self, model_name: str = "qwen2.5:7b", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.base_url = base_url
        self.generate_url = f"{base_url}/api/generate"
        self.chat_url = f"{base_url}/api/chat"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """
        生成式对话（单次问答）

        Args:
            prompt: 用户输入的提示词
            system_prompt: 可选的系统提示词，用于设定角色或规则

        Returns:
            模型生成的文本回复
        """
        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False
        }

        # 如果提供了系统提示词，则加入请求体
        if system_prompt:
            payload["system"] = system_prompt

        try:
            response = requests.post(self.generate_url, json=payload)
            response.raise_for_status()  # 如果状态码不是200则抛出异常
            return response.json().get("response", "")

        except requests.exceptions.RequestException as e:
            print(f"[OllamaClient] 请求失败: {e}")
            return ""

# 实例化一个全局客户端，方便其他模块直接导入使用
ollama_client = OllamaClient()

if __name__ == "__main__":
    # 简单的自测代码
    reply = ollama_client.generate("你好，请用一句话介绍你自己")
    print(f"模型回复: {reply}")
