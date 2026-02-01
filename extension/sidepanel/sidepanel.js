/**
 * RealtimeTranscriptionApp - Chrome拡張版
 *
 * タブ音声専用に簡素化したメインアプリケーション
 */
class RealtimeTranscriptionApp {
    constructor() {
        this.audioCapture = null;
        this.wsClient = null;
        this.uiController = new UIController();

        this.isRecording = false;
        this.disconnectTimeout = null;

        // タブ共有固定
        this.inputSource = "tab";

        // 処理オプション
        this.processingOptions = {
            enableHiragana: false,
            enableTranslation: false,
            enableSummary: false,
        };

        this.init();
    }

    /**
     * 初期化
     */
    async init() {
        try {
            // 設定を読み込む
            const config = await chrome.storage.sync.get({
                apiServerUrl: 'ws://localhost:5001',
                defaultHiragana: false,
                defaultTranslation: false
            });

            this.apiServerUrl = config.apiServerUrl;
            this.processingOptions.enableHiragana = config.defaultHiragana;
            this.processingOptions.enableTranslation = config.defaultTranslation;

            // チェックボックスのデフォルト値を設定
            document.getElementById("enable-hiragana").checked = this.processingOptions.enableHiragana;
            document.getElementById("enable-translation").checked = this.processingOptions.enableTranslation;

            // セクションの表示/非表示を設定
            this.uiController.toggleHiraganaSection(this.processingOptions.enableHiragana);
            this.uiController.toggleTranslationSection(this.processingOptions.enableTranslation);

            // 処理オプションのイベントリスナー
            document.getElementById("enable-hiragana").addEventListener("change", (e) => {
                this.processingOptions.enableHiragana = e.target.checked;
                this.uiController.toggleHiraganaSection(e.target.checked);
            });

            document.getElementById("enable-translation").addEventListener("change", (e) => {
                this.processingOptions.enableTranslation = e.target.checked;
                this.uiController.toggleTranslationSection(e.target.checked);
            });

            // ボタンイベント設定
            this.uiController.startButton.addEventListener("click", () => {
                this.start();
            });

            this.uiController.stopButton.addEventListener("click", () => {
                this.stop();
            });

            this.uiController.downloadButton.addEventListener("click", () => {
                this.uiController.downloadTranscript(
                    this.inputSource,
                    this.processingOptions
                );
            });

            this.uiController.setStatus("準備完了", "success");
            console.log("✅ Chrome拡張版 初期化完了");
        } catch (error) {
            console.error("初期化エラー:", error);
            this.uiController.showToast("初期化に失敗しました", "error");
        }
    }

    /**
     * 録音開始
     */
    async start() {
        try {
            // APIサーバーURL検証
            if (!this.apiServerUrl || this.apiServerUrl === '') {
                this.uiController.showToast(
                    "APIサーバーURLが設定されていません。拡張機能の設定画面で設定してください。",
                    "error",
                    8000
                );
                return;
            }

            // 既存のaudioCaptureが存在する場合はクリーンアップ
            if (this.audioCapture) {
                this.audioCapture.stop();
                this.audioCapture = null;
            }

            // 新しいセッション開始前にすべてのテキストをクリア
            this.uiController.clearAllText();

            this.uiController.setStatus("接続中...", "info");
            this.uiController.showToast("WebSocket接続中...", "info");

            // WebSocket接続（設定から取得したURL）
            const wsUrl = `${this.apiServerUrl}/ws/transcribe-stream-cumulative`;
            this.wsClient = new WebSocketClient(wsUrl);

            this.wsClient.on("connected", (sessionId) => {
                console.log("セッション開始:", sessionId);
                this.uiController.startSession();
                this.uiController.showToast("セッション開始", "success");
            });

            this.wsClient.on("progress", (step, message) => {
                this.uiController.showToast(message, "info", 2000);
            });

            this.wsClient.on("transcription_update", (data) => {
                this.uiController.updateTranscription(data);
            });

            this.wsClient.on("accumulating", (data) => {
                this.uiController.setStatus(`音声蓄積中... (${data.accumulated_seconds.toFixed(1)}秒)`, "info");
            });

            this.wsClient.on("error", (message) => {
                this.uiController.showToast(message, "error", 5000);
            });

            this.wsClient.on("session_end", (data) => {
                console.log("セッション終了:", data);

                // 最終結果をUIに反映（暫定テキストが確定テキストに移行）
                if (data.transcription || data.hiragana || data.translation) {
                    this.uiController.updateTranscription({
                        transcription: data.transcription || {},
                        hiragana: data.hiragana || {},
                        translation: data.translation || {},
                        performance: data.performance || {},
                    });
                }

                this.uiController.setStatus("セッション終了", "success");
                this.uiController.showToast("処理が完了しました", "success");

                // ダウンロードボタンを有効化
                if (this.uiController.transcriptionHistory.length > 0) {
                    this.uiController.downloadButton.disabled = false;
                    console.log("📥 ダウンロードボタンを有効化しました");
                }

                // session_end受信後にクリーンアップ
                this.forceCleanup();
            });

            await this.wsClient.connect();

            // 処理オプションを送信
            this.wsClient.sendOptions(this.processingOptions);
            console.log("処理オプション送信:", this.processingOptions);

            // 音声キャプチャ開始
            this.audioCapture = new AudioCapture({
                sampleRate: 16000,
                chunkDurationMs: 3000,
            });

            let chunkCount = 0;

            // chrome.tabCaptureを使用（Phase 6.2.3で実装）
            await this.audioCapture.startFromChromeTab(
                (audioData) => {
                    // 音声チャンクを送信
                    chunkCount++;
                    console.log(`📺 音声チャンク送信: ${chunkCount}個目 (${audioData.byteLength} bytes)`);
                    this.wsClient.sendAudioChunk(audioData);
                },
                (volumeDb) => {
                    // 音量レベルを更新
                    this.uiController.updateVolumeLevel(volumeDb);
                },
            );

            this.isRecording = true;
            this.uiController.setButtonsState(true);
            this.uiController.setStatus("タブ音声解析中...", "recording");
            this.uiController.showToast("タブ音声の文字起こしを開始しました", "success");
        } catch (error) {
            console.error("開始エラー:", error);

            // エラータイプに応じたメッセージ
            if (error.name === "NotAllowedError") {
                this.uiController.showToast(
                    "タブキャプチャがキャンセルされました。",
                    "error",
                    5000
                );
                this.uiController.setStatus("タブキャプチャがキャンセルされました", "error");
            } else if (error.message && error.message.includes("音声トラック")) {
                this.uiController.showToast(error.message, "error", 8000);
                this.uiController.setStatus("音声トラックが見つかりません", "error");
            } else if (error.message && error.message.includes("WebSocket")) {
                // WebSocket接続エラー
                this.uiController.showToast(
                    `サーバーに接続できませんでした: ${this.apiServerUrl}\n\nサーバーが起動しているか確認してください。`,
                    "error",
                    10000
                );
                this.uiController.setStatus("サーバー接続エラー", "error");
            } else {
                this.uiController.showToast(
                    error.message || "開始に失敗しました",
                    "error",
                    5000
                );
                this.uiController.setStatus("エラー", "error");
            }

            // クリーンアップ
            this.forceCleanup();
        }
    }

    /**
     * 録音停止
     */
    async stop() {
        this.isRecording = false;
        this.uiController.setButtonsState(false);
        this.uiController.setStatus("タブ共有停止中...", "info");

        // バッファに残っている音声データを最終チャンクとして送信
        if (this.audioCapture) {
            const remainingBuffer = await this.audioCapture.getRemainingBuffer();
            if (remainingBuffer && this.wsClient) {
                console.log("📤 最終チャンクを送信");
                this.wsClient.sendAudioChunk(remainingBuffer);
                this.uiController.showToast("最終チャンクを送信しました", "info", 2000);
            }

            // 音声キャプチャを停止
            this.audioCapture.stop();
            this.audioCapture = null;
        }

        this.uiController.setStatus("処理中の結果を待機中...", "info");
        this.uiController.showToast("タブ共有を停止しました。処理完了を待っています...", "info", 2000);

        // サーバーに終了メッセージを送信
        if (this.wsClient) {
            this.wsClient.sendEndMessage();

            // タイムアウト処理: 10秒待ってもsession_endが来なければ強制切断
            this.disconnectTimeout = setTimeout(() => {
                console.warn("⚠️ session_end待機タイムアウト。強制切断します。");
                this.forceCleanup();
                this.uiController.showToast("タイムアウトにより接続を切断しました", "warning");
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
}

// アプリケーション起動
document.addEventListener("DOMContentLoaded", () => {
    new RealtimeTranscriptionApp();
});
