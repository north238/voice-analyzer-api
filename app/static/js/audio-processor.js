/**
 * AudioWorkletProcessor - 音声処理ワークレット
 *
 * ScriptProcessorNodeの代替として、別スレッドで音声処理を行います。
 * メインスレッドをブロックせず、より正確なタイミング制御が可能です。
 */
class VoiceAnalyzerProcessor extends AudioWorkletProcessor {
    constructor() {
        super();

        // 音声バッファ
        this.audioBuffer = [];

        // チャンク設定（メインスレッドから受信）
        this.chunkSize = 0;

        // メッセージハンドラー
        this.port.onmessage = (event) => {
            if (event.data.type === "setChunkSize") {
                this.chunkSize = event.data.chunkSize;
            } else if (event.data.type === "getRemainingBuffer") {
                // 残りバッファを返信
                this.port.postMessage({
                    type: "remainingBuffer",
                    data: this.audioBuffer.slice(), // コピーして送信
                    sampleCount: this.audioBuffer.length,
                });
                // バッファをクリア
                this.audioBuffer = [];
            }
        };
    }

    /**
     * 音声データの処理
     *
     * @param {Float32Array[][]} inputs - 入力音声データ
     * @param {Float32Array[][]} _outputs - 出力音声データ（未使用）
     * @param {Object} _parameters - パラメータ（未使用）
     * @returns {boolean} - true: 処理継続, false: 処理終了
     */
    process(inputs, _outputs, _parameters) {
        const input = inputs[0];

        if (input.length > 0) {
            const channelData = input[0]; // モノラル（チャンネル0）

            // 音量レベル計算（RMS）
            let sum = 0;
            for (let i = 0; i < channelData.length; i++) {
                sum += channelData[i] * channelData[i];
            }
            const rms = Math.sqrt(sum / channelData.length);
            const volumeDb = 20 * Math.log10(rms + 1e-10);

            // 音量レベルをメインスレッドに送信
            this.port.postMessage({
                type: "volumeLevel",
                volumeDb: volumeDb,
            });

            // バッファに蓄積
            this.audioBuffer.push(...channelData);

            // チャンクサイズに達したら送信
            if (this.chunkSize > 0 && this.audioBuffer.length >= this.chunkSize) {
                const chunkData = this.audioBuffer.slice(0, this.chunkSize);
                this.audioBuffer = this.audioBuffer.slice(this.chunkSize);

                // チャンクデータをメインスレッドに送信
                this.port.postMessage({
                    type: "audioChunk",
                    data: chunkData,
                });
            }
        }

        // 処理を継続
        return true;
    }

    /**
     * 残りのバッファを取得
     */
    static get parameterDescriptors() {
        return [];
    }
}

// ワークレットプロセッサーを登録
registerProcessor("voice-analyzer-processor", VoiceAnalyzerProcessor);
