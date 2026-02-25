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

        // 入力ソース管理
        this.inputSource = "microphone"; // 'microphone' または 'video'
        this.videoElement = null;

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
            // デバイス一覧を取得
            await this.uiController.populateDeviceSelector();

            // 入力ソース切り替えイベント
            document.querySelectorAll('input[name="inputSource"]').forEach((radio) => {
                radio.addEventListener("change", (e) => {
                    this.inputSource = e.target.value;
                    this.toggleInputUI();
                });
            });

            // 動画ファイル選択イベント
            const videoFileInput = document.getElementById("video-file-input");
            if (videoFileInput) {
                videoFileInput.addEventListener("change", (e) => {
                    this.loadVideoFile(e.target.files[0]);
                });
            }

            // サンプル動画ボタンのイベント
            document.querySelectorAll(".btn-sample").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const videoUrl = btn.getAttribute("data-video");
                    this.loadVideoUrl(videoUrl);
                });
            });

            // 処理オプションのイベントリスナー
            document.getElementById("enable-hiragana").addEventListener("change", (e) => {
                this.processingOptions.enableHiragana = e.target.checked;
                this.uiController.toggleHiraganaSection(e.target.checked);
            });

            document.getElementById("enable-translation").addEventListener("change", (e) => {
                this.processingOptions.enableTranslation = e.target.checked;
                this.uiController.toggleTranslationSection(e.target.checked);
            });

            document.getElementById("enable-summary").addEventListener("change", (e) => {
                this.processingOptions.enableSummary = e.target.checked;
                this.uiController.toggleSummarySection(e.target.checked);
            });

            // ボタンイベント設定（1ボタントグル）
            this.uiController.startButton.addEventListener("click", () => {
                if (this.isRecording) {
                    this.stop();
                } else {
                    this.start();
                }
            });

            this.uiController.downloadButton.addEventListener("click", () => {
                this.uiController.downloadTranscript(
                    this.inputSource,
                    this.processingOptions
                );
            });

            // 要約ボタンのイベントリスナー
            document.getElementById("summary-button").addEventListener("click", () => {
                this.requestSummary();
            });

            this.uiController.setStatus("success");
        } catch (error) {
            console.error("初期化エラー:", error);
            this.uiController.showToast("初期化に失敗しました", "error");
        }
    }

    /**
     * 入力ソースUIの切り替え
     */
    toggleInputUI() {
        const micControls = document.getElementById("microphone-controls");
        const videoControls = document.getElementById("video-controls");
        const tabControls = document.getElementById("tab-controls");
        const volumeMeter = document.getElementById("volume-meter");
        const videoTimeDisplay = document.getElementById("video-time-display");

        if (this.inputSource === "microphone") {
            micControls.style.display = "flex";
            videoControls.style.display = "none";
            tabControls.style.display = "none";
            if (volumeMeter) volumeMeter.style.display = "block";
            if (videoTimeDisplay) videoTimeDisplay.style.display = "none";
            this.uiController.setStatus("success");
        } else if (this.inputSource === "video") {
            micControls.style.display = "none";
            videoControls.style.display = "block";
            tabControls.style.display = "none";
            if (volumeMeter) volumeMeter.style.display = "none";
            if (videoTimeDisplay) videoTimeDisplay.style.display = "block";
            this.uiController.setStatus("info");
        } else if (this.inputSource === "tab") {
            micControls.style.display = "none";
            videoControls.style.display = "none";
            tabControls.style.display = "block";
            if (volumeMeter) volumeMeter.style.display = "block";
            if (videoTimeDisplay) videoTimeDisplay.style.display = "none";
            this.uiController.setStatus("success");
        }
    }

    /**
     * 動画の再生時間表示を更新
     */
    _updateVideoTime() {
        const currentEl = document.getElementById("video-current-time");
        const totalEl = document.getElementById("video-total-time");
        if (!currentEl || !totalEl || !this.videoElement) return;
        currentEl.textContent = this._formatVideoTime(this.videoElement.currentTime);
        totalEl.textContent = this._formatVideoTime(this.videoElement.duration || 0);
    }

    /**
     * 秒数を MM:SS 形式にフォーマット
     *
     * @param {number} seconds
     * @returns {string}
     */
    _formatVideoTime(seconds) {
        const m = Math.floor(seconds / 60);
        const s = Math.floor(seconds % 60);
        return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    }

    /**
     * 動画ファイルを読み込む
     *
     * @param {File} file - 動画ファイル
     */
    loadVideoFile(file) {
        if (!file) {
            return;
        }

        // ファイルタイプチェック
        if (!file.type.startsWith("video/")) {
            this.uiController.showToast("動画ファイルを選択してください", "error");
            return;
        }

        try {
            // 既存の動画要素を削除して新しく作成（createMediaElementSourceのエラー回避）
            const oldVideoElement = document.getElementById("video-player");
            if (oldVideoElement) {
                // 以前のURLを解放
                if (oldVideoElement.src && oldVideoElement.src.startsWith("blob:")) {
                    URL.revokeObjectURL(oldVideoElement.src);
                }
                oldVideoElement.pause();
                oldVideoElement.src = "";
                oldVideoElement.load();
                oldVideoElement.remove();
            }

            // 新しい動画要素を作成
            const videoControls = document.getElementById("video-controls");
            const newVideoElement = document.createElement("video");
            newVideoElement.id = "video-player";
            newVideoElement.controls = true;
            newVideoElement.style.display = "block";

            const url = URL.createObjectURL(file);
            newVideoElement.src = url;
            videoControls.appendChild(newVideoElement);

            this.videoElement = newVideoElement;

            // 動画終了時の自動停止イベントを追加
            this.videoElement.addEventListener("ended", () => {
                if (this.isRecording) {
                    console.log("🎬 動画再生終了 - 自動停止します");
                    this.uiController.showToast("動画が終了しました。自動的に停止します。", "info");
                    this.stop();
                }
            });

            // 再生時間の表示更新
            this.videoElement.addEventListener("loadedmetadata", () => this._updateVideoTime());
            this.videoElement.addEventListener("timeupdate", () => this._updateVideoTime());

            this.videoElement.load();

            this.uiController.setStatus("success");
            this.uiController.showToast(`動画ファイル読み込み: ${file.name}`, "success");
        } catch (error) {
            console.error("動画ファイル読み込みエラー:", error);
            this.uiController.showToast("動画ファイルの読み込みに失敗しました", "error");
        }
    }

    /**
     * 動画URLを読み込む
     *
     * @param {string} url - 動画URL
     */
    loadVideoUrl(url) {
        if (!url) {
            return;
        }

        try {
            // 既存の動画要素を削除して新しく作成（createMediaElementSourceのエラー回避）
            const oldVideoElement = document.getElementById("video-player");
            if (oldVideoElement) {
                oldVideoElement.pause();
                oldVideoElement.src = "";
                oldVideoElement.load();
                oldVideoElement.remove();
            }

            // 新しい動画要素を作成
            const videoControls = document.getElementById("video-controls");
            const newVideoElement = document.createElement("video");
            newVideoElement.id = "video-player";
            newVideoElement.controls = true;
            newVideoElement.style.display = "block";
            newVideoElement.src = url;
            videoControls.appendChild(newVideoElement);

            this.videoElement = newVideoElement;

            // 動画終了時の自動停止イベントを追加
            this.videoElement.addEventListener("ended", () => {
                if (this.isRecording) {
                    console.log("🎬 動画再生終了 - 自動停止します");
                    this.uiController.showToast("動画が終了しました。自動的に停止します。", "info");
                    this.stop();
                }
            });

            // 再生時間の表示更新
            this.videoElement.addEventListener("loadedmetadata", () => this._updateVideoTime());
            this.videoElement.addEventListener("timeupdate", () => this._updateVideoTime());

            this.videoElement.load();

            const fileName = url.split("/").pop();
            this.uiController.setStatus("success");
            this.uiController.showToast(`サンプル動画読み込み: ${fileName}`, "success");
        } catch (error) {
            console.error("動画URL読み込みエラー:", error);
            this.uiController.showToast("動画の読み込みに失敗しました", "error");
        }
    }

    /**
     * 録音開始
     */
    async start() {
        try {
            // 既存のaudioCaptureが存在する場合はクリーンアップ
            if (this.audioCapture) {
                this.audioCapture.stop();
                this.audioCapture = null;
            }

            // 新しいセッション開始前にすべてのテキストをクリア
            this.uiController.clearAllText();

            this.uiController.setStatus("info");

            // WebSocket接続
            const wsUrl = `ws://${window.location.host}/ws/transcribe-stream-cumulative`;
            this.wsClient = new WebSocketClient(wsUrl);

            this.wsClient.on("connected", (sessionId) => {
                console.log("セッション開始:", sessionId);
                this.uiController.startSession();
                this.uiController.setStatus("recording");
            });

            this.wsClient.on("progress", (step, message) => {
                this.uiController.setStatus("processing");
            });

            this.wsClient.on("transcription_update", (data) => {
                this.uiController.updateTranscription(data);
                // 文字起こし更新後は録音中に戻す
                if (this.isRecording) {
                    this.uiController.setStatus("recording");
                }
            });

            this.wsClient.on("error", (message) => {
                this.uiController.showToast(message, "error", 5000);
            });

            this.wsClient.on("session_end", (data) => {
                console.log("セッション終了:", data);

                // 最終ひらがな・翻訳を保存（ダウンロード用）
                const finalHiragana = data.hiragana?.confirmed || "";
                const finalTranslation = data.translation?.confirmed || "";
                this.uiController.setFinalResults(finalHiragana, finalTranslation);

                // 最終結果をUIに反映（暫定テキストが確定テキストに移行）
                if (data.transcription || data.hiragana || data.translation) {
                    this.uiController.updateTranscription({
                        transcription: data.transcription || {},
                        hiragana: data.hiragana || {},
                        translation: data.translation || {},
                        is_final: true,
                    });
                }

                // 自動要約結果の表示
                if (data.summary) {
                    this.uiController.showSummary(data.summary);
                }

                this.uiController.setStatus("success");

                // ダウンロードボタンを有効化
                if (this.uiController.transcriptionHistory.length > 0) {
                    this.uiController.downloadButton.disabled = false;
                    console.log("📥 ダウンロードボタンを有効化しました");

                    // 要約ボタンを有効化（手動要約用）
                    document.getElementById("summary-button").disabled = false;
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

            // 入力ソースに応じて処理を分岐
            if (this.inputSource === "microphone") {
                // マイクから音声キャプチャ
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
                    },
                );
            } else if (this.inputSource === "video") {
                // 動画から音声キャプチャ
                if (!this.videoElement || !this.videoElement.src) {
                    throw new Error("動画ファイルを選択してください");
                }

                // video要素を再作成（createMediaElementSourceのエラー回避）
                // Web Audio APIの制約: 一度使われたvideo要素は再利用できない
                const oldSrc = this.videoElement.src;

                // 古い要素を削除
                this.videoElement.pause();
                this.videoElement.remove();

                // 新しい要素を作成
                const videoControls = document.getElementById("video-controls");
                const newVideoElement = document.createElement("video");
                newVideoElement.id = "video-player";
                newVideoElement.controls = true;
                newVideoElement.style.display = "block";
                newVideoElement.src = oldSrc;
                videoControls.appendChild(newVideoElement);

                this.videoElement = newVideoElement;

                // 動画終了時の自動停止イベントを再設定
                this.videoElement.addEventListener("ended", () => {
                    if (this.isRecording) {
                        console.log("🎬 動画再生終了 - 自動停止します");
                        this.uiController.showToast("動画が終了しました。自動的に停止します。", "info");
                        this.stop();
                    }
                });

                // 再生時間の表示更新（再設定）
                this.videoElement.addEventListener("loadedmetadata", () => this._updateVideoTime());
                this.videoElement.addEventListener("timeupdate", () => this._updateVideoTime());

                // 動画のロードを待つ
                console.log("🎥 動画ロード開始...");
                await new Promise((resolve, reject) => {
                    // 既にロード済みの場合
                    if (this.videoElement.readyState >= 2) {
                        console.log("✅ 動画は既にロード済み");
                        resolve();
                        return;
                    }

                    // ロード待機
                    const onLoadedData = () => {
                        console.log("✅ 動画ロード完了");
                        cleanup();
                        resolve();
                    };

                    const onError = (error) => {
                        console.error("❌ 動画ロードエラー:", error);
                        cleanup();
                        reject(new Error("動画の読み込みに失敗しました"));
                    };

                    const cleanup = () => {
                        this.videoElement.removeEventListener("loadeddata", onLoadedData);
                        this.videoElement.removeEventListener("error", onError);
                    };

                    this.videoElement.addEventListener("loadeddata", onLoadedData, { once: true });
                    this.videoElement.addEventListener("error", onError, { once: true });
                    this.videoElement.load();
                });

                await this.audioCapture.startFromVideo(
                    this.videoElement,
                    (audioData) => {
                        // 音声チャンクを送信
                        chunkCount++;
                        console.log(`🎥 音声チャンク送信: ${chunkCount}個目 (${audioData.byteLength} bytes)`);
                        this.wsClient.sendAudioChunk(audioData);
                    },
                    (volumeDb) => {
                        // 音量レベルを更新
                        this.uiController.updateVolumeLevel(volumeDb);
                    },
                );

                // 動画再生開始
                this.videoElement.play();
            } else if (this.inputSource === "tab") {
                // タブ共有から音声キャプチャ
                await this.audioCapture.startFromTabCapture(
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
            }

            this.isRecording = true;
            this.uiController.setButtonsState(true);
            this.uiController.setStatus("recording");
        } catch (error) {
            console.error("開始エラー:", error);

            // エラータイプに応じたメッセージ
            if (error.name === "NotAllowedError") {
                if (this.inputSource === "tab") {
                    this.uiController.showToast("タブ共有がキャンセルされました。", "error", 5000);
                } else {
                    this.uiController.showToast(
                        "マイクへのアクセスが拒否されました。ブラウザの設定を確認してください。",
                        "error",
                        5000,
                    );
                }
            } else if (error.name === "NotFoundError") {
                this.uiController.showToast("マイクが見つかりません。デバイスを接続してください。", "error", 5000);
            } else if (error.message && error.message.includes("音声トラック")) {
                this.uiController.showToast(error.message, "error", 8000);
            } else {
                this.uiController.showToast(error.message || "開始に失敗しました", "error", 5000);
            }

            this.uiController.setStatus("success");

            // クリーンアップ
            this.forceCleanup();
        }
    }

    /**
     * 録音停止
     */
    async stop() {
        this.isRecording = false;
        // 処理完了待ち中はボタンを無効化（グレー）。forceCleanup() で再び有効になる
        this.uiController.startButton.disabled = true;

        this.uiController.setStatus("processing");

        // 動画の場合は再生を停止
        if (this.inputSource === "video" && this.videoElement) {
            this.videoElement.pause();
        }

        // バッファに残っている音声データを最終チャンクとして送信
        if (this.audioCapture) {
            const remainingBuffer = await this.audioCapture.getRemainingBuffer();
            if (remainingBuffer && this.wsClient) {
                console.log("📤 最終チャンクを送信");
                this.wsClient.sendAudioChunk(remainingBuffer);
            }

            // 音声キャプチャを停止
            this.audioCapture.stop();
            this.audioCapture = null;
        }

        // サーバーに終了メッセージを送信
        if (this.wsClient) {
            this.wsClient.sendEndMessage();

            // タイムアウト処理: 20秒待ってもsession_endが来なければ強制切断
            this.disconnectTimeout = setTimeout(async () => {
                console.warn("⚠️ session_end待機タイムアウト。強制切断します。");

                // タイムアウト時に暫定テキストを強制的に確定に移行
                this.uiController.forceFinalize();

                // ひらがな・翻訳を一括処理（サーバーに問い合わせ）
                await this._processFinalText();

                this.forceCleanup();
                this.uiController.setStatus("success");
                this.uiController.showToast("タイムアウトにより接続を切断しました", "warning");
            }, 20000);
        }
    }

    /**
     * 手動要約リクエスト
     */
    async requestSummary() {
        const confirmedText = this.uiController.getConfirmedText();
        if (!confirmedText) {
            this.uiController.showToast("要約するテキストがありません", "warning");
            return;
        }

        this.uiController.showSummaryLoading(true);
        document.getElementById("summary-button").disabled = true;

        try {
            const httpUrl = `http://${window.location.host}`;
            const response = await fetch(`${httpUrl}/summarize`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: confirmedText }),
            });

            const result = await response.json();

            if (result.status === 'success') {
                this.uiController.showSummary(result.summary);
            } else {
                this.uiController.showToast(result.message || "要約に失敗しました", "error");
            }
        } catch (error) {
            console.error("要約エラー:", error);
            this.uiController.showToast("要約リクエストに失敗しました", "error");
        } finally {
            this.uiController.showSummaryLoading(false);
            document.getElementById("summary-button").disabled = false;
        }
    }

    /**
     * セッション終了時にひらがな・翻訳を一括処理
     */
    async _processFinalText() {
        const confirmedText = this.uiController.currentConfirmedText;
        if (!confirmedText) return;

        const options = this.processingOptions || {};
        const needsHiragana = options.enableHiragana;
        const needsTranslation = options.enableTranslation;
        if (!needsHiragana && !needsTranslation) return;

        try {
            const apiUrl = `http://${window.location.host}/process-text`;
            const response = await fetch(apiUrl, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    text: confirmedText,
                    hiragana: !!needsHiragana,
                    translation: !!needsTranslation,
                }),
            });
            if (!response.ok) return;
            const result = await response.json();
            if (result.hiragana) {
                this.uiController._updateHiraganaDisplay(result.hiragana);
            }
            if (result.translation && this.uiController.translationText) {
                this.uiController.translationText.classList.remove("processing");
                this.uiController.translationText.textContent = result.translation;
            }
            console.log("✅ タイムアウト後の一括処理完了");
        } catch (e) {
            console.warn("⚠️ タイムアウト後の一括処理に失敗:", e);
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

        // 動画の停止とクリーンアップ
        if (this.inputSource === "video" && this.videoElement) {
            this.videoElement.pause();
            // ObjectURLの解放は不要（ユーザーが再度使用する可能性があるため）
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
document.addEventListener("DOMContentLoaded", () => {
    new RealtimeTranscriptionApp();
});
