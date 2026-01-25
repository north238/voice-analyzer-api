from transformers import MarianMTModel, MarianTokenizer
from config import settings
from utils.logger import logger
from typing import Optional
import re


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

    def _preprocess_text(self, text: str) -> tuple[str, dict]:
        """
        翻訳前の前処理（数字・電話番号の保護）

        Args:
            text: 前処理対象のテキスト

        Returns:
            (前処理後のテキスト, 置換マップ)
        """
        replacements = {}
        processed_text = text

        # 電話番号パターンを検出して保護
        phone_pattern = r"\d{10,11}"
        phones = re.findall(phone_pattern, processed_text)
        for i, phone in enumerate(phones):
            placeholder = f"__PHONE_{i}__"
            replacements[placeholder] = phone
            processed_text = processed_text.replace(phone, placeholder, 1)
            logger.debug(f"電話番号を保護: {phone} → {placeholder}")

        return processed_text, replacements

    def _postprocess_text(self, text: str, replacements: dict) -> str:
        """
        翻訳後の後処理（保護した要素を復元）

        Args:
            text: 後処理対象のテキスト
            replacements: 置換マップ

        Returns:
            後処理後のテキスト
        """
        processed_text = text
        for placeholder, original in replacements.items():
            processed_text = processed_text.replace(placeholder, original)
            logger.debug(f"保護要素を復元: {placeholder} → {original}")

        return processed_text

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

            # 前処理（数字・電話番号の保護）
            preprocessed_text, replacements = self._preprocess_text(text)

            # 文単位で分割して翻訳（精度向上のため）
            sentences = self._split_into_sentences(preprocessed_text)

            if len(sentences) > 1:
                # 複数文の場合は1文ずつ翻訳
                logger.info(f"📝 {len(sentences)}個の文に分割して翻訳します")
                translated = self._translate_long_text(preprocessed_text)
            else:
                # 単一文の場合は通常の翻訳処理
                logger.info(f"🔄 翻訳開始: {preprocessed_text[:50]}...")
                translated = self._translate_chunk(preprocessed_text)
                logger.info(f"✅ 翻訳完了: {translated[:50]}...")

            # 後処理（保護要素の復元）
            final_text = self._postprocess_text(translated, replacements)

            return final_text

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

        # 翻訳生成（品質向上パラメータ）
        # Phase 4最適化: num_beams を 6 → 4 に変更（処理時間30%削減）
        translated_tokens = self.model.generate(
            **inputs,
            num_beams=4,  # ビームサーチで品質向上（6→4に削減、速度向上）
            no_repeat_ngram_size=3,  # 3-gramの繰り返しを防止
            repetition_penalty=1.3,  # 繰り返しペナルティを緩和（1.5→1.3）
            length_penalty=0.8,  # 短めの翻訳を優先（1.0→0.8）
            early_stopping=True,  # 早期終了を有効化
            max_length=512,  # 最大出力長
            temperature=0.7,  # 多様性を追加（デフォルトは1.0だが0.7で安定性向上）
        )

        # デコード
        translated_text = self.tokenizer.decode(
            translated_tokens[0], skip_special_tokens=True
        )

        return translated_text

    def _split_into_sentences(self, text: str) -> list[str]:
        """
        テキストを文単位で分割

        Args:
            text: 分割対象のテキスト

        Returns:
            文のリスト
        """
        # 句点で分割
        sentences = text.split("。")
        result = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                result.append(
                    sentence + "。" if not sentence.endswith("。") else sentence
                )
        return result

    def _translate_long_text(self, text: str) -> str:
        """
        長文を分割して翻訳

        Args:
            text: 長文テキスト

        Returns:
            分割翻訳された結果を結合したテキスト
        """
        # 文単位で分割
        sentences = self._split_into_sentences(text)

        logger.info(f"📦 {len(sentences)}個の文に分割しました")

        # 各文を個別に翻訳
        translated_sentences = []
        for i, sentence in enumerate(sentences):
            logger.info(f"🔄 文 {i+1}/{len(sentences)} を翻訳中: {sentence[:30]}...")
            translated = self._translate_chunk(sentence)
            translated_sentences.append(translated)
            logger.info(f"✅ 翻訳結果: {translated[:50]}...")

        # 結合して返す
        result = " ".join(translated_sentences)
        logger.info(f"✅ 全文の翻訳完了")
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
