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
                console.log('WebSocket接続成功');
            };

            this.ws.onmessage = (event) => {
                const data = JSON.parse(event.data);
                this._handleMessage(data);

                if (data.type === 'connected') {
                    this.sessionId = data.session_id;
                    resolve();
                }
            };

            this.ws.onerror = (error) => {
                console.error('WebSocketエラー:', error);
                reject(error);
            };

            this.ws.onclose = (event) => {
                this.isConnected = false;
                console.log('WebSocket接続終了');

                if (event.code !== 1000) { // 正常終了以外
                    if (this.onErrorCallback) {
                        this.onErrorCallback('接続が切断されました。再試行してください。');
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
        switch (data.type) {
            case 'connected':
                if (this.onConnectedCallback) {
                    this.onConnectedCallback(data.session_id);
                }
                break;

            case 'progress':
                if (this.onProgressCallback) {
                    this.onProgressCallback(data.step, data.message);
                }
                break;

            case 'transcription_update':
                if (this.onTranscriptionUpdateCallback) {
                    this.onTranscriptionUpdateCallback(data);
                }
                break;

            case 'accumulating':
                if (this.onAccumulatingCallback) {
                    this.onAccumulatingCallback(data);
                }
                break;

            case 'error':
                if (this.onErrorCallback) {
                    this.onErrorCallback(data.message);
                }
                break;

            case 'session_end':
                if (this.onSessionEndCallback) {
                    this.onSessionEndCallback(data);
                }
                break;
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
     * WebSocket接続を切断
     */
    disconnect() {
        if (this.isConnected) {
            this.ws.send(JSON.stringify({ type: 'end' }));
            // 正常終了コード(1000)を指定して切断
            this.ws.close(1000, 'Normal closure');
        }
    }

    /**
     * イベントコールバックを設定
     *
     * @param {string} event - イベント名
     * @param {Function} callback - コールバック関数
     */
    on(event, callback) {
        switch (event) {
            case 'connected':
                this.onConnectedCallback = callback;
                break;
            case 'progress':
                this.onProgressCallback = callback;
                break;
            case 'transcription_update':
                this.onTranscriptionUpdateCallback = callback;
                break;
            case 'accumulating':
                this.onAccumulatingCallback = callback;
                break;
            case 'error':
                this.onErrorCallback = callback;
                break;
            case 'session_end':
                this.onSessionEndCallback = callback;
                break;
        }
    }
}
