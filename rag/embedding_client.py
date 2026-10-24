import requests

class EmbeddingClient:
    """
    本地 Embedding 客户端
    负责将文本转换为向量（数字列表）
    """

    def __init__(self, model_name: str = "nomic-embed-text", base_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.embed_url = f"{base_url}/api/embeddings"

    def get_embedding(self, text: str) -> list[float]:
        """
        将单条文本转换为向量

        Args:
            text: 需要转换的文本

        Returns:
            768维的浮点数列表（向量）
        """
        if not text or not text.strip():
            return []

        payload = {
            "model": self.model_name,
            "prompt": text
        }

        try:
            response = requests.post(self.embed_url, json=payload)
            response.raise_for_status()
            return response.json().get("embedding", [])

        except requests.exceptions.RequestException as e:
            print(f"[EmbeddingClient] 请求失败: {e}")
            return []

# 实例化全局客户端
embedding_client = EmbeddingClient()

if __name__ == "__main__":
    test_text = "FastAPI 是一个现代、高性能的 Python Web 框架"

    print(f"正在将文本转换为向量: '{test_text}'")
    vector = embedding_client.get_embedding(test_text)

    if vector:
        print(f"✅ 转换成功！")
        print(f"向量维度: {len(vector)}")
        print(f"前5个数值: {vector[:5]}")
    else:
        print("❌ 转换失败")
