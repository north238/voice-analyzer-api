import tempfile
import subprocess
import os
import whisper
from fastapi import UploadFile, HTTPException

model = whisper.load_model("small")


async def transcribe_audio(file: UploadFile) -> str:
    tmp_path = None
    converted_path = None
    try:
        # 一時ファイル作成
        suffix = os.path.splitext(file.filename)[1] or ".webm"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(await file.read())
            tmp_path = tmp.name

        # ffmpegで16kHz/モノラルに変換（Whisper最適化）
        converted_path = tmp_path.rsplit(".", 1)[0] + "_16k.wav"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-i",
                tmp_path,
                "-ar",
                "16000",
                "-ac",
                "1",
                "-af",
                "loudnorm",  # 音量正規化
                converted_path,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Whisperで文字起こし
        result = model.transcribe(
            converted_path,
            language="ja",
            temperature=0.0,
            best_of=5,
            beam_size=10,
            patience=0.2,
            fp16=False,
            condition_on_previous_text=True,
        )

        # 音声チェック（無音・ノイズ判定）
        if "segments" in result and result["segments"]:
            first_segment = result["segments"][0]
            no_speech_prob = first_segment.get("no_speech_prob", 0)
            avg_logprob = first_segment.get("avg_logprob", 0)

            # 音声として有効かどうかを簡易判定
            if no_speech_prob > 0.9:
                raise ValueError("音声が認識されませんでした（無音またはノイズの可能性）")
        else:
            raise ValueError("音声解析結果が取得できませんでした")


        # 補正処理（誤変換修正など）
        text = result["text"]
        corrections = {
            "無天下": "無添加",
            "生石犬": "生石鹸",
        }
        for wrong, correct in corrections.items():
            text = text.replace(wrong, correct)

        return text

    except subprocess.CalledProcessError:
        raise HTTPException(status_code=500, detail="音声変換に失敗しました。")

    finally:
        # 一時ファイル削除
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
        if converted_path and os.path.exists(converted_path):
            os.remove(converted_path)
