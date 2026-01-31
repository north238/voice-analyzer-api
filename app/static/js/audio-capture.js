/**
 * AudioCapture - Web Audio APIを使った音声キャプチャ
 *
 * マイクから音声を16kHz, モノラル, 16-bit PCMでキャプチャし、
 * WAVフォーマットに変換してコールバックに渡します。
 *
 * AudioWorkletを使用して、メインスレッドをブロックせずに音声処理を行います。
 */
class AudioCapture {
    constructor(config = {}) {
        this.sampleRate = config.sampleRate || 16000;
        this.chunkDurationMs = config.chunkDurationMs || 3000;

        this.mediaStream = null;
        this.audioContext = null;
        this.workletNode = null;
        this.isCapturing = false;

        this.onChunkCallback = null;
        this.onVolumeLevelCallback = null;
        this._remainingBufferResolve = null;
    }

    /**
     * 音声キャプチャを開始（マイクから）
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
                },
            });

            await this._setupAudioProcessing(this.mediaStream, onChunk, onVolumeLevel);

            console.log("✅ AudioWorkletベースの音声キャプチャを開始（マイク）");
        } catch (error) {
            console.error("音声キャプチャ開始エラー:", error);
            throw error;
        }
    }

    /**
     * 音声キャプチャを開始（動画要素から）
     *
     * @param {HTMLVideoElement} videoElement - 動画要素
     * @param {Function} onChunk - チャンク生成時のコールバック
     * @param {Function} onVolumeLevel - 音量レベル更新時のコールバック
     */
    async startFromVideo(videoElement, onChunk, onVolumeLevel) {
        try {
            if (!videoElement || !videoElement.src) {
                throw new Error("有効な動画要素が指定されていません");
            }

            // 既存のAudioContextがあれば閉じる
            if (this.audioContext) {
                await this.audioContext.close();
                this.audioContext = null;
            }

            // AudioContext作成（16kHzにリサンプリング）
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate,
            });

            // 動画要素から音声ストリームを取得
            const source = this.audioContext.createMediaElementSource(videoElement);
            const dest = this.audioContext.createMediaStreamDestination();

            // 動画の音声をスピーカーにも出力（ユーザーが音声を聞けるように）
            source.connect(this.audioContext.destination);
            source.connect(dest);

            this.mediaStream = dest.stream;

            await this._setupAudioProcessing(this.mediaStream, onChunk, onVolumeLevel);

            console.log("✅ AudioWorkletベースの音声キャプチャを開始（動画）");
        } catch (error) {
            console.error("動画からの音声キャプチャ開始エラー:", error);
            throw error;
        }
    }

    /**
     * 音声キャプチャを開始（タブ共有から）
     *
     * @param {Function} onChunk - チャンク生成時のコールバック
     * @param {Function} onVolumeLevel - 音量レベル更新時のコールバック
     */
    async startFromTabCapture(onChunk, onVolumeLevel) {
        try {
            // タブ共有ダイアログを表示
            this.mediaStream = await navigator.mediaDevices.getDisplayMedia({
                video: true, // videoをtrueにしないとChromeでエラーになる場合がある
                audio: {
                    sampleRate: this.sampleRate,
                    channelCount: 1,
                    echoCancellation: false,
                    noiseSuppression: false,
                    autoGainControl: false,
                },
            });

            // 音声トラックがあるか確認
            const audioTracks = this.mediaStream.getAudioTracks();
            if (audioTracks.length === 0) {
                throw new Error(
                    "音声トラックが見つかりません。タブ共有時に「音声を共有」にチェックを入れてください。",
                );
            }

            console.log("✅ タブ共有の音声トラックを取得:", audioTracks[0].label);

            await this._setupAudioProcessing(this.mediaStream, onChunk, onVolumeLevel);

            console.log("✅ AudioWorkletベースの音声キャプチャを開始（タブ共有）");
        } catch (error) {
            console.error("タブ共有からの音声キャプチャ開始エラー:", error);

            // ユーザーがキャンセルした場合
            if (error.name === "NotAllowedError") {
                throw new Error("タブ共有がキャンセルされました");
            }

            throw error;
        }
    }

    /**
     * 音声処理パイプラインのセットアップ（共通処理）
     *
     * @param {MediaStream} mediaStream - 音声ストリーム
     * @param {Function} onChunk - チャンク生成時のコールバック
     * @param {Function} onVolumeLevel - 音量レベル更新時のコールバック
     */
    async _setupAudioProcessing(mediaStream, onChunk, onVolumeLevel) {
        // AudioContext作成（まだ作成されていない場合）
        if (!this.audioContext) {
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: this.sampleRate,
            });
        }

        // AudioWorkletプロセッサーをロード
        await this.audioContext.audioWorklet.addModule("/static/js/audio-processor.js");

        const source = this.audioContext.createMediaStreamSource(mediaStream);

        // AudioWorkletNodeを作成
        this.workletNode = new AudioWorkletNode(this.audioContext, "voice-analyzer-processor");

        // チャンクサイズをワークレットに送信
        const samplesPerChunk = (this.sampleRate * this.chunkDurationMs) / 1000;
        this.workletNode.port.postMessage({
            type: "setChunkSize",
            chunkSize: samplesPerChunk,
        });

        // ワークレットからのメッセージを処理
        this.workletNode.port.onmessage = (event) => {
            this._handleWorkletMessage(event.data);
        };

        source.connect(this.workletNode);
        this.workletNode.connect(this.audioContext.destination);

        this.onChunkCallback = onChunk;
        this.onVolumeLevelCallback = onVolumeLevel;
        this.isCapturing = true;
    }

    /**
     * ワークレットからのメッセージを処理
     *
     * @param {Object} data - メッセージデータ
     */
    _handleWorkletMessage(data) {
        switch (data.type) {
            case "volumeLevel":
                if (this.onVolumeLevelCallback) {
                    this.onVolumeLevelCallback(data.volumeDb);
                }
                break;

            case "audioChunk":
                // Float32 → Int16 PCMに変換
                const pcmData = this._float32ToInt16(new Float32Array(data.data));

                // WAVヘッダーを追加
                const wavData = this._createWavFile(pcmData);

                if (this.onChunkCallback) {
                    this.onChunkCallback(wavData);
                }
                break;

            case "remainingBuffer":
                // getRemainingBuffer()からのPromiseを解決
                if (this._remainingBufferResolve) {
                    if (data.data && data.data.length > 0) {
                        const pcmData = this._float32ToInt16(new Float32Array(data.data));
                        const wavData = this._createWavFile(pcmData);
                        this._remainingBufferResolve(wavData);
                    } else {
                        this._remainingBufferResolve(null);
                    }
                    this._remainingBufferResolve = null;
                }
                break;

            default:
                console.warn("⚠️ 未知のワークレットメッセージ:", data.type);
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
            int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
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
        this._writeString(view, 0, "RIFF");
        view.setUint32(4, 36 + dataSize, true);
        this._writeString(view, 8, "WAVE");
        this._writeString(view, 12, "fmt ");
        view.setUint32(16, 16, true); // fmt chunkサイズ
        view.setUint16(20, 1, true); // PCM
        view.setUint16(22, numChannels, true);
        view.setUint32(24, sampleRate, true);
        view.setUint32(28, byteRate, true);
        view.setUint16(32, blockAlign, true);
        view.setUint16(34, bitsPerSample, true);
        this._writeString(view, 36, "data");
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
     * バッファに残っているデータを取得（最終チャンク用）
     *
     * @returns {Promise<ArrayBuffer|null>} - 残りの音声データ（WAV形式）、なければnull
     */
    async getRemainingBuffer() {
        if (!this.workletNode) {
            return null;
        }

        return new Promise((resolve) => {
            // Promiseのresolveをコールバックとして保存
            this._remainingBufferResolve = (data) => {
                if (!data || data.byteLength === 0) {
                    resolve(null);
                    return;
                }

                // 最小チャンクサイズ（0.5秒 = 8000サンプル = 16000bytes）
                const minBytes = this.sampleRate * 0.5 * 2; // Int16 = 2 bytes/sample
                if (data.byteLength < minBytes) {
                    console.log(`⚠️ 残りバッファが小さすぎます: ${data.byteLength}bytes (最小: ${minBytes}bytes)`);
                    resolve(null);
                    return;
                }

                const sampleCount = (data.byteLength - 44) / 2; // WAVヘッダー44bytes除く
                console.log(
                    `📦 残りバッファを取得: ${sampleCount}サンプル (${(sampleCount / this.sampleRate).toFixed(2)}秒)`,
                );
                resolve(data);
            };

            // ワークレットに残りバッファを要求
            this.workletNode.port.postMessage({
                type: "getRemainingBuffer",
            });

            // タイムアウト処理（1秒待ってもレスポンスがなければnull）
            setTimeout(() => {
                if (this._remainingBufferResolve) {
                    console.warn("⚠️ 残りバッファの取得がタイムアウトしました");
                    this._remainingBufferResolve = null;
                    resolve(null);
                }
            }, 1000);
        });
    }

    /**
     * 音声キャプチャを停止
     */
    stop() {
        this.isCapturing = false;

        if (this.workletNode) {
            this.workletNode.disconnect();
            this.workletNode.port.close();
            this.workletNode = null;
        }

        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }

        if (this.mediaStream) {
            this.mediaStream.getTracks().forEach((track) => track.stop());
            this.mediaStream = null;
        }
    }
}
