from langchain_text_splitters import RecursiveCharacterTextSplitter

class TextSplitter:
    """
    文本切分器
    负责将长文本切分为适合大模型处理的小块（Chunks）
    """

    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 100):
        """
        Args:
            chunk_size: 每个文本块的最大字符数（中文一个字算1个字符）
            chunk_overlap: 相邻两个文本块之间重叠的字符数（防止一句话被切断导致语义丢失）
        """
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", "。", "！", "？", " ", ""],  # 优先按段落、句子切分
            length_function=len,
        )

    def split_text(self, text: str) -> list[str]:
        """
        将长文本切分为多个小块

        Args:
            text: 原始长文本

        Returns:
            切分后的文本块列表
        """
        if not text or not text.strip():
            return []
        return self.splitter.split_text(text)

# 实例化一个默认的切分器，方便后续直接导入使用
text_splitter = TextSplitter()

if __name__ == "__main__":
    # 模拟一篇长文章
    dummy_article = "".join(
        f"第{i}段内容不同，用于测试文本切分效果。"
        for i in range(100)
    )

    chunks = text_splitter.split_text(dummy_article)

    print(f"原始文本长度: {len(dummy_article)}")
    print(f"切分后的块数: {len(chunks)}")
    print("-" * 30)
    for i, chunk in enumerate(chunks):
        print(f"\n[块 {i+1}] 长度: {len(chunk)}")
        print(f"开头 120 字符: {chunk[:120]}")
        print(f"结尾 120 字符: {chunk[-120:]}")
    if len(chunks) >= 2:
        chunk_a = chunks[0]
        chunk_b = chunks[1]

        overlap = 0
        max_length = min(len(chunk_a), len(chunk_b))

        for length in range(max_length, 0, -1):
            if chunk_a[-length:] == chunk_b[:length]:
                overlap = length
                break

        print(f"\n块 1 和块 2 的重叠字符数：{overlap}")
