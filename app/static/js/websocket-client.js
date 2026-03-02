/**
 * WebSocketClient - WebSocket通信の管理
 *
 * サーバーとのWebSocket接続を確立し、
 * 音声チャンクの送信と文字起こし結果の受信を行います。
 */
class WebSocketClient {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.sessionId = null;
        this.isConnected = false;

        this.onConnectedCallback = null;
        this.onProgressCallback = null;
        this.onTranscriptionUpdateCallback = null;
        this.onErrorCallback = null;
        this.onSessionEndCallback = null;
        this.onAccumulatingCallback = null;
        this.onSummaryResultCallback = null;
    }

    /**
     * WebSocket接続を確立
     *
     * @returns {Promise} - 接続確立のPromise
     */
    async connect() {
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                this.isConnected = true;
                console.log("WebSocket接続成功");
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this._handleMessage(data);

                if (data.type === "connected") {
                    this.sessionId = data.session_id;
                    resolve();
                }
            };

            this.ws.onerror = (error) => {
                console.error("WebSocketエラー:", error);
                reject(error);
            };

            this.ws.onclose = (event) => {
                this.isConnected = false;
                console.log("WebSocket接続終了");

                if (event.code !== 1000) {
                    // 正常終了以外
                    if (this.onErrorCallback) {
                        this.onErrorCallback("接続が切断されました。再試行してください。");
                    }
                }
            };
        });
    }

    /**
     * サーバーからのメッセージを処理
     *
     * @param {Object} data - 受信メッセージ
     */
    _handleMessage(data) {
        console.log("📨 受信メッセージ:", data.type, data);

        switch (data.type) {
            case "connected":
                console.log("✅ WebSocket接続確立:", data.session_id);
                if (this.onConnectedCallback) {
                    this.onConnectedCallback(data.session_id);
                }
                break;

            case "progress":
                console.log("⏳ 処理中:", data.step, data.message);
                if (this.onProgressCallback) {
                    this.onProgressCallback(data.step, data.message);
                }
                break;

            case "transcription_update":
                console.log("📝 文字起こし更新:", data);
                if (this.onTranscriptionUpdateCallback) {
                    this.onTranscriptionUpdateCallback(data);
                }
                break;

            case "accumulating":
                const elapsedTime = data.session_elapsed_seconds ?? data.accumulated_seconds;
                console.log("📦 録音中:", elapsedTime, "秒");
                if (this.onAccumulatingCallback) {
                    this.onAccumulatingCallback(data);
                }
                break;

            case "error":
                console.error("❌ エラー:", data.message);
                if (this.onErrorCallback) {
                    this.onErrorCallback(data.message);
                }
                break;

            case "session_end":
                console.log("🏁 セッション終了:", data);
                if (this.onSessionEndCallback) {
                    this.onSessionEndCallback(data);
                }
                break;

            case "summary_result":
                console.log("📋 要約結果受信:", data);
                if (this.onSummaryResultCallback) {
                    this.onSummaryResultCallback(data);
                }
                break;

            case "options_received":
                console.log("✅ 処理オプション受信確認");
                break;

            case "skipped":
                // 無音チャンクのスキップ通知（ログのみ）
                console.log("⏭️ チャンクスキップ:", data.reason);
                break;

            case "buffer_trim_start":
                console.log("⚙️ バッファトリミング開始:", data.message);
                if (this.uiController) {
                    this.uiController.showTrimIndicator();
                }
                break;

            case "buffer_trim_complete":
                console.log("✅ バッファトリミング完了:", data.message);
                if (this.uiController) {
                    this.uiController.hideTrimIndicator();
                }
                break;

            default:
                console.warn("⚠️ 未知のメッセージタイプ:", data.type);
        }
    }

    /**
     * 音声チャンクを送信
     *
     * @param {ArrayBuffer} arrayBuffer - 音声データ
     */
    sendAudioChunk(arrayBuffer) {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(arrayBuffer);
        }
    }

    /**
     * 処理オプションを送信
     *
     * @param {Object} options - 処理オプション
     */
    sendOptions(options) {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            console.log("📤 処理オプション送信:", options);
            this.ws.send(
                JSON.stringify({
                    type: "options",
                    hiragana: options.enableHiragana,
                    translation: options.enableTranslation,
                    summary: options.enableSummary,
                })
            );
        }
    }

    /**
     * 終了メッセージを送信（WebSocketは切断しない）
     */
    sendEndMessage() {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            console.log("📤 終了メッセージ送信");
            this.ws.send(JSON.stringify({ type: "end" }));
        }
    }

    /**
     * WebSocket接続を切断
     */
    disconnect() {
        if (this.isConnected && this.ws.readyState === WebSocket.OPEN) {
            console.log("🔌 WebSocket切断");
            // 正常終了コード(1000)を指定して切断
            this.ws.close(1000, "Normal closure");
        }
        this.isConnected = false;
    }

    /**
     * イベントコールバックを設定
     *
     * @param {string} event - イベント名
     * @param {Function} callback - コールバック関数
     */
    on(event, callback) {
        switch (event) {
            case "connected":
                this.onConnectedCallback = callback;
                break;
            case "progress":
                this.onProgressCallback = callback;
                break;
            case "transcription_update":
                this.onTranscriptionUpdateCallback = callback;
                break;
            case "accumulating":
                this.onAccumulatingCallback = callback;
                break;
            case "error":
                this.onErrorCallback = callback;
                break;
            case "session_end":
                this.onSessionEndCallback = callback;
                break;
            case "summary_result":
                this.onSummaryResultCallback = callback;
                break;
        }
    }
}
