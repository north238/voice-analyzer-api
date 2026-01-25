/**
 * RealtimeTranscriptionApp - メインアプリケーション
 *
 * 各コンポーネントを統合し、リアルタイム音声文字起こしを実現します。
 */
class RealtimeTranscriptionApp {
    constructor() {
        this.audioCapture = null;
        this.wsClient = null;
        this.uiController = new UIController();

        this.isRecording = false;
        this.disconnectTimeout = null;

        this.init();
    }

    /**
     * 初期化
     */
    async init() {
        try {
            // デバイス一覧を取得
            await this.uiController.populateDeviceSelector();

            // ボタンイベント設定
            this.uiController.startButton.addEventListener('click', () => {
                this.start();
            });

            this.uiController.stopButton.addEventListener('click', () => {
                this.stop();
            });

            this.uiController.setStatus('準備完了。「開始」ボタンを押してください。', 'success');
            this.uiController.showToast('準備完了。「開始」ボタンを押してください。', 'success');
        } catch (error) {
            console.error('初期化エラー:', error);
            this.uiController.showToast('初期化に失敗しました', 'error');
        }
    }

    /**
     * 録音開始
     */
    async start() {
        try {
            this.uiController.setStatus('接続中...', 'info');
            this.uiController.showToast('WebSocket接続中...', 'info');

            // WebSocket接続
            const wsUrl = `ws://${window.location.host}/ws/transcribe-stream-cumulative`;
            this.wsClient = new WebSocketClient(wsUrl);

            this.wsClient.on('connected', (sessionId) => {
                console.log('セッション開始:', sessionId);
                this.uiController.showToast('セッション開始', 'success');
            });

            this.wsClient.on('progress', (step, message) => {
                this.uiController.showToast(message, 'info', 2000);
            });

            this.wsClient.on('transcription_update', (data) => {
                this.uiController.updateTranscription(data);
            });

            this.wsClient.on('accumulating', (data) => {
                this.uiController.setStatus(
                    `音声蓄積中... (${data.accumulated_seconds.toFixed(1)}秒)`,
                    'info'
                );
            });

            this.wsClient.on('error', (message) => {
                this.uiController.showToast(message, 'error', 5000);
            });

            this.wsClient.on('session_end', (data) => {
                console.log('セッション終了:', data);
                this.uiController.setStatus('セッション終了', 'success');
                this.uiController.showToast('処理が完了しました', 'success');

                // session_end受信後にクリーンアップ
                this.forceCleanup();
            });

            await this.wsClient.connect();

            // 音声キャプチャ開始
            this.audioCapture = new AudioCapture({
                sampleRate: 16000,
                chunkDurationMs: 3000,
            });

            let chunkCount = 0;
            await this.audioCapture.start(
                (audioData) => {
                    // 音声チャンクを送信
                    chunkCount++;
                    console.log(`🎤 音声チャンク送信: ${chunkCount}個目 (${audioData.byteLength} bytes)`);
                    this.wsClient.sendAudioChunk(audioData);
                },
                (volumeDb) => {
                    // 音量レベルを更新
                    this.uiController.updateVolumeLevel(volumeDb);
                }
            );

            this.isRecording = true;
            this.uiController.setButtonsState(true);
            this.uiController.setStatus('録音中...', 'recording');
            this.uiController.showToast('録音を開始しました', 'success');

        } catch (error) {
            console.error('開始エラー:', error);

            // エラータイプに応じたメッセージ
            if (error.name === 'NotAllowedError') {
                this.uiController.showToast(
                    'マイクへのアクセスが拒否されました。ブラウザの設定を確認してください。',
                    'error',
                    5000
                );
            } else if (error.name === 'NotFoundError') {
                this.uiController.showToast(
                    'マイクが見つかりません。デバイスを接続してください。',
                    'error',
                    5000
                );
            } else {
                this.uiController.showToast(error.message || '開始に失敗しました', 'error', 5000);
            }

            // クリーンアップ
            this.forceCleanup();
        }
    }

    /**
     * 録音停止
     */
    stop() {
        // 音声キャプチャを停止（これ以上チャンクを送信しない）
        if (this.audioCapture) {
            this.audioCapture.stop();
            this.audioCapture = null;
        }

        this.isRecording = false;
        this.uiController.setButtonsState(false);
        this.uiController.setStatus('処理中の結果を待機中...', 'info');
        this.uiController.showToast('録音を停止しました。処理完了を待っています...', 'info', 2000);

        // サーバーに終了メッセージを送信
        if (this.wsClient) {
            this.wsClient.sendEndMessage();

            // タイムアウト処理: 10秒待ってもsession_endが来なければ強制切断
            this.disconnectTimeout = setTimeout(() => {
                console.warn('⚠️ session_end待機タイムアウト。強制切断します。');
                this.forceCleanup();
                this.uiController.showToast('タイムアウトにより接続を切断しました', 'warning');
            }, 10000);
        }
    }

    /**
     * 強制クリーンアップ
     */
    forceCleanup() {
        if (this.disconnectTimeout) {
            clearTimeout(this.disconnectTimeout);
            this.disconnectTimeout = null;
        }

        if (this.wsClient) {
            this.wsClient.disconnect();
            this.wsClient = null;
        }

        if (this.audioCapture) {
            this.audioCapture.stop();
            this.audioCapture = null;
        }

        this.isRecording = false;
        this.uiController.setButtonsState(false);
    }

    /**
     * クリーンアップ（後方互換性のため維持）
     */
    cleanup() {
        this.forceCleanup();
    }
}

// アプリケーション起動
document.addEventListener('DOMContentLoaded', () => {
    new RealtimeTranscriptionApp();
});
