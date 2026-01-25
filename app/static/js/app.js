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
        } catch (error) {
            console.error('初期化エラー:', error);
            this.uiController.showError('初期化に失敗しました');
        }
    }

    /**
     * 録音開始
     */
    async start() {
        try {
            this.uiController.setStatus('接続中...', 'info');

            // WebSocket接続
            const wsUrl = `ws://${window.location.host}/ws/transcribe-stream-cumulative`;
            this.wsClient = new WebSocketClient(wsUrl);

            this.wsClient.on('connected', (sessionId) => {
                console.log('セッション開始:', sessionId);
            });

            this.wsClient.on('progress', (step, message) => {
                this.uiController.setStatus(message, 'info');
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
                this.uiController.showError(message);
            });

            this.wsClient.on('session_end', (data) => {
                console.log('セッション終了:', data);
                this.uiController.setStatus('セッション終了', 'success');
            });

            await this.wsClient.connect();

            // 音声キャプチャ開始
            this.audioCapture = new AudioCapture({
                sampleRate: 16000,
                chunkDurationMs: 3000,
            });

            await this.audioCapture.start(
                (audioData) => {
                    // 音声チャンクを送信
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

        } catch (error) {
            console.error('開始エラー:', error);

            // エラータイプに応じたメッセージ
            if (error.name === 'NotAllowedError') {
                this.uiController.showError(
                    'マイクへのアクセスが拒否されました。ブラウザの設定を確認してください。'
                );
            } else if (error.name === 'NotFoundError') {
                this.uiController.showError(
                    'マイクが見つかりません。デバイスを接続してください。'
                );
            } else {
                this.uiController.showError(error.message || '開始に失敗しました');
            }

            // クリーンアップ
            this.cleanup();
        }
    }

    /**
     * 録音停止
     */
    stop() {
        this.cleanup();
        this.uiController.setStatus('停止しました。', 'success');
    }

    /**
     * クリーンアップ
     */
    cleanup() {
        if (this.audioCapture) {
            this.audioCapture.stop();
            this.audioCapture = null;
        }

        if (this.wsClient) {
            this.wsClient.disconnect();
            this.wsClient = null;
        }

        this.isRecording = false;
        this.uiController.setButtonsState(false);
    }
}

// アプリケーション起動
document.addEventListener('DOMContentLoaded', () => {
    new RealtimeTranscriptionApp();
});
