/**
 * AudioCapture - Web Audio APIを使った音声キャプチャ
 *
 * マイクから音声を16kHz, モノラル, 16-bit PCMでキャプチャし、
 * WAVフォーマットに変換してコールバックに渡します。
 */
class AudioCapture {
    constructor(config = {}) {
        this.sampleRate = config.sampleRate || 16000;
        this.chunkDurationMs = config.chunkDurationMs || 3000;

        this.mediaStream = null;
        this.audioContext = null;
        this.scriptProcessor = null;
        this.audioBuffer = [];
        this.isCapturing = false;

        this.onChunkCallback = null;
        this.onVolumeLevelCallback = null;
    }

    /**
     * 音声キャプチャを開始
     *
     * @param {Function} onChunk - チャンク生成時のコールバック
     * @param {Function} onVolumeLevel - 音量レベル更新時のコールバック
     */
    async start(onChunk, onVolumeLevel) {
        try {
            // マイクアクセス要求
            this.mediaStream = await navigator.mediaDevices.getUserMedia({
                audio: {
                    sampleRate: this.sampleRate,
                    channelCount: 1, // モノラル
                    echoCancellation: true,
                    noiseSuppression: true,
                }
            });

            // AudioContext作成（16kHzにリサンプリング）
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate
            });

            const source = this.audioContext.createMediaStreamSource(this.mediaStream);

            // ScriptProcessorNodeでPCMデータ取得
            this.scriptProcessor = this.audioContext.createScriptProcessor(4096, 1, 1);
            this.scriptProcessor.onaudioprocess = (event) => {
                this._processAudio(event);
            };

            source.connect(this.scriptProcessor);
            this.scriptProcessor.connect(this.audioContext.destination);

            this.onChunkCallback = onChunk;
            this.onVolumeLevelCallback = onVolumeLevel;
            this.isCapturing = true;

        } catch (error) {
            console.error('音声キャプチャ開始エラー:', error);
            throw error;
        }
    }

    /**
     * 音声データの処理
     *
     * @param {AudioProcessingEvent} event
     */
    _processAudio(event) {
        const inputData = event.inputBuffer.getChannelData(0); // Float32Array

        // 音量レベル計算（RMS）
        const rms = Math.sqrt(
            inputData.reduce((sum, val) => sum + val * val, 0) / inputData.length
        );
        const volumeDb = 20 * Math.log10(rms + 1e-10);

        if (this.onVolumeLevelCallback) {
            this.onVolumeLevelCallback(volumeDb);
        }

        // バッファに蓄積
        this.audioBuffer.push(...inputData);

        // バッファサイズ制限（最大10秒分）
        const maxBufferSize = this.sampleRate * 10;
        if (this.audioBuffer.length > maxBufferSize) {
            this.audioBuffer = this.audioBuffer.slice(-maxBufferSize);
        }

        // チャンクサイズに達したら送信
        const samplesPerChunk = (this.sampleRate * this.chunkDurationMs) / 1000;
        if (this.audioBuffer.length >= samplesPerChunk) {
            const chunkData = this.audioBuffer.slice(0, samplesPerChunk);
            this.audioBuffer = this.audioBuffer.slice(samplesPerChunk);

            // Float32 → Int16 PCMに変換
            const pcmData = this._float32ToInt16(chunkData);

            // WAVヘッダーを追加
            const wavData = this._createWavFile(pcmData);

            if (this.onChunkCallback) {
                this.onChunkCallback(wavData);
            }
        }
    }

    /**
     * Float32ArrayをInt16Arrayに変換
     *
     * @param {Float32Array} float32Array
     * @returns {Int16Array}
     */
    _float32ToInt16(float32Array) {
        const int16Array = new Int16Array(float32Array.length);
        for (let i = 0; i < float32Array.length; i++) {
            const s = Math.max(-1, Math.min(1, float32Array[i]));
            int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        return int16Array;
    }

    /**
     * WAVファイルを作成
     *
     * @param {Int16Array} pcmData - PCMデータ
     * @returns {ArrayBuffer} - WAVファイルのバイナリデータ
     */
    _createWavFile(pcmData) {
        const sampleRate = this.sampleRate;
        const numChannels = 1;
        const bitsPerSample = 16;
        const byteRate = (sampleRate * numChannels * bitsPerSample) / 8;
        const blockAlign = (numChannels * bitsPerSample) / 8;
        const dataSize = pcmData.length * 2;

        const buffer = new ArrayBuffer(44 + dataSize);
        const view = new DataView(buffer);

        // WAVヘッダー
        this._writeString(view, 0, 'RIFF');
        view.setUint32(4, 36 + dataSize, true);
        this._writeString(view, 8, 'WAVE');
        this._writeString(view, 12, 'fmt ');
        view.setUint32(16, 16, true); // fmt chunkサイズ
        view.setUint16(20, 1, true); // PCM
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, bitsPerSample, true);
        this._writeString(view, 36, 'data');
        view.setUint32(40, dataSize, true);

        // PCMデータ
        const offset = 44;
        for (let i = 0; i < pcmData.length; i++) {
            view.setInt16(offset + i * 2, pcmData[i], true);
        }

        return buffer;
    }

    /**
     * DataViewに文字列を書き込む
     *
     * @param {DataView} view
     * @param {number} offset
     * @param {string} string
     */
    _writeString(view, offset, string) {
        for (let i = 0; i < string.length; i++) {
            view.setUint8(offset + i, string.charCodeAt(i));
        }
    }

    /**
     * 音声キャプチャを停止
     */
    stop() {
        this.isCapturing = false;

        if (this.scriptProcessor) {
            this.scriptProcessor.disconnect();
            this.scriptProcessor = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach(track => track.stop());
            this.mediaStream = null;
        }
    }
}
