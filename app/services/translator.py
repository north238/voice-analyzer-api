from transformers import MarianMTModel, MarianTokenizer
from config import settings
from utils.logger import logger
from typing import Optional


class Translator:
    """日英翻訳を行うクラス（Helsinki-NLP/opus-mt-ja-en）"""

    def __init__(self):
        self.model: Optional[MarianMTModel] = None
        self.tokenizer: Optional[MarianTokenizer] = None
        self.model_name = settings.TRANSLATION_MODEL
        self.max_length = settings.MAX_TRANSLATION_LENGTH
        self.device = settings.TRANSLATION_DEVICE

    def _load_model(self):
        """翻訳モデルとトークナイザをロード（遅延ロード）"""
        if self.model is not None and self.tokenizer is not None:
            return

        try:
            logger.info(f"🔄 翻訳モデルをロード中: {self.model_name}")
            self.tokenizer = MarianTokenizer.from_pretrained(self.model_name)
            self.model = MarianMTModel.from_pretrained(self.model_name)
            self.model.to(self.device)
            self.model.eval()
            logger.info(f"✅ 翻訳モデルのロード完了")
        except Exception as e:
            logger.exception(f"❌ 翻訳モデルのロードに失敗: {e}")
            raise RuntimeError(f"翻訳モデルのロードに失敗しました: {e}")

    def translate_text(self, text: str) -> str:
        """
        日本語テキストを英語に翻訳

        Args:
            text: 翻訳対象の日本語テキスト

        Returns:
            翻訳された英語テキスト
        """
        if not text or not text.strip():
            logger.warning("⚠️ 空のテキストが渡されました")
            return ""

        try:
            # モデルのロード（初回のみ）
            self._load_model()

            # 長文の場合は分割処理
            if len(text) > self.max_length:
                logger.info(
                    f"📝 長文を分割処理します（{len(text)}文字 > {self.max_length}文字）"
                )
                return self._translate_long_text(text)

            # 通常の翻訳処理
            logger.info(f"🔄 翻訳開始: {text[:50]}...")
            translated = self._translate_chunk(text)
            logger.info(f"✅ 翻訳完了: {translated[:50]}...")
            return translated

        except Exception as e:
            logger.exception(f"❌ 翻訳中にエラー発生: {e}")
            raise RuntimeError(f"翻訳処理に失敗しました: {e}")

    def _translate_chunk(self, text: str) -> str:
        """
        単一チャンクの翻訳処理

        Args:
            text: 翻訳対象テキスト（max_length以内）

        Returns:
            翻訳結果
        """
        # トークナイズ
        inputs = self.tokenizer(
            text, return_tensors="pt", padding=True, truncation=True, max_length=512
        ).to(self.device)

        # 翻訳生成
        translated_tokens = self.model.generate(**inputs)

        # デコード
        translated_text = self.tokenizer.decode(
            translated_tokens[0], skip_special_tokens=True
        )

        return translated_text

    def _translate_long_text(self, text: str) -> str:
        """
        長文を分割して翻訳

        Args:
            text: 長文テキスト

        Returns:
            分割翻訳された結果を結合したテキスト
        """
        # 句点で分割
        sentences = text.split("。")
        chunks = []
        current_chunk = ""

        for sentence in sentences:
            if not sentence.strip():
                continue

            # チャンクサイズを超える場合は次のチャンクへ
            if len(current_chunk) + len(sentence) + 1 > self.max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = sentence + "。"
            else:
                current_chunk += sentence + "。"

        # 残りを追加
        if current_chunk:
            chunks.append(current_chunk)

        logger.info(f"📦 {len(chunks)}個のチャンクに分割しました")

        # 各チャンクを翻訳
        translated_chunks = []
        for i, chunk in enumerate(chunks):
            logger.info(f"🔄 チャンク {i+1}/{len(chunks)} を翻訳中...")
            translated = self._translate_chunk(chunk)
            translated_chunks.append(translated)

        # 結合して返す
        result = " ".join(translated_chunks)
        logger.info(f"✅ 全チャンクの翻訳完了")
        return result


# シングルトンインスタンス
_translator_instance: Optional[Translator] = None


def get_translator() -> Translator:
    """翻訳インスタンスを取得（シングルトン）"""
    global _translator_instance
    if _translator_instance is None:
        _translator_instance = Translator()
    return _translator_instance


def translate_text(text: str) -> str:
    """
    テキストを翻訳する便利関数

    Args:
        text: 翻訳対象の日本語テキスト

    Returns:
        翻訳された英語テキスト
    """
    translator = get_translator()
    return translator.translate_text(text)
