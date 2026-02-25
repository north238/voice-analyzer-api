/**
 * UIController - UI要素の更新管理
 *
 * DOM要素の参照を保持し、表示内容を更新します。
 */
class UIController {
    constructor() {
        // DOM要素の参照
        this.startButton = document.getElementById("start-button");
        this.stopButton = this.startButton; // 1ボタン方式：同じ要素を参照
        this.downloadButton = document.getElementById("download-button");
        this.statusDot = document.getElementById("status-dot");
        this.volumeMeter = document.getElementById("volume-meter");
        this.volumeBar = document.getElementById("volume-bar");

        this.transcriptionText = document.getElementById("transcription-text");
        this.hiraganaText = document.getElementById("hiragana-text");

        this.translationText = document.getElementById("translation-text");
        this.hiraganaSection = document.querySelector(".hiragana-results");
        this.translationSection = document.getElementById("translation-section");
        this.hiraganaTextMobile = document.getElementById("hiragana-text-mobile");
        this.translationTextMobile = document.getElementById("translation-text-mobile");

        this.deviceSelector = document.getElementById("device-selector");
        this.toastContainer = document.getElementById("toast-container");

        // タイピングアニメーション用の状態管理
        this.previousConfirmedText = "";
        this.previousTentativeText = "";
        this.previousHiraganaConfirmed = "";
        this.previousHiraganaTentative = "";

        this.typingTimers = [];

        // 現在の確定テキスト（累積）
        this.currentConfirmedText = "";
        this.currentHiraganaConfirmed = "";

        // セッションデータ（ダウンロード用）
        this.sessionStartTime = null;
        this.transcriptionHistory = [];
        this.finalHiragana = "";
        this.finalTranslation = "";
        this.finalSummary = "";

        // 要約関連DOM
        this.summaryCard = document.getElementById("summary-card");
        this.summaryText = document.getElementById("summary-text");
        this.summaryLoading = document.getElementById("summary-loading");
    }

    /**
     * セッション開始
     * セッション開始時刻を記録
     */
    startSession() {
        this.sessionStartTime = Date.now();
        this.transcriptionHistory = [];
        this.finalHiragana = "";
        this.finalTranslation = "";
        this.finalSummary = "";
        // 要約テキストをリセット（カードは常時表示）
        if (this.summaryText) this.summaryText.textContent = "";
        // ひらがなセクションが表示中なら変換中インジケーターを表示
        if (this.hiraganaText) {
            this.hiraganaText.textContent = "";
            this.hiraganaText.classList.add("processing");
        }
        // 翻訳セクションが表示中なら翻訳中インジケーターを表示
        if (this.hiraganaTextMobile) { this.hiraganaTextMobile.innerHTML = ""; }
        if (this.translationTextMobile) { this.translationTextMobile.textContent = ""; }
        if (this.translationText) {
            this.translationText.textContent = "";
            this.translationText.classList.add("processing");
        }
        console.log("📝 セッション開始時刻を記録しました");
    }

    /**
     * ステータスドットの色を設定
     *
     * @param {string} type - ステータスタイプ (info, success, error, recording, processing)
     */
    setStatus(type = "info") {
        this.statusDot.className = `status-dot ${type}`;
    }

    /**
     * 音量レベルを更新
     *
     * @param {number} volumeDb - 音量レベル（dB）
     */
    updateVolumeLevel(volumeDb) {
        // -60dB ~ 0dBを0~100%に正規化
        const normalized = Math.max(0, Math.min(100, ((volumeDb + 60) / 60) * 100));
        // バーの幅（形）のみで音量を表現
        this.volumeBar.style.width = `${normalized}%`;
    }

    /**
     * 文字起こし結果を更新
     *
     * @param {Object} data - 文字起こしデータ
     */
    updateTranscription(data) {
        console.log("🖥️ UI更新:", data);

        const transcription = data.transcription || {};
        const hiragana = data.hiragana || {};
        const translation = data.translation || {};

        const newConfirmedText = transcription.confirmed || "";
        const newTentativeText = transcription.tentative || "";
        const newHiraganaConfirmed = hiragana.confirmed || "";
        const newHiraganaTentative = hiragana.tentative || "";

        // デバッグログ: WebSocket受信データを確認
        if (newConfirmedText) {
            console.log("🔍 WebSocket受信データ:");
            console.log("  confirmed.length:", newConfirmedText.length);
            console.log("  confirmed (先頭100文字):", newConfirmedText.slice(0, 100));
            console.log("  confirmed (末尾100文字):", newConfirmedText.slice(-100));
        }
        const newConfirmedTranslation = translation.confirmed || "";
        const newTentativeTranslation = translation.tentative || "";

        // 既存のタイピングアニメーションをキャンセル
        this._cancelTypingAnimations();

        // セッション終了時（is_finalフラグまたは暫定が空で確定が来た場合）は、最終確定テキストを反映
        const isSessionEnd = data.is_final || (!newTentativeText && this.previousTentativeText);
        if (isSessionEnd) {
            console.log("🏁 セッション終了: 暫定テキストを確定に移行");

            // サーバーからの最終確定テキストと、ローカルの確定+暫定を比較して長い方を採用
            const localFinalText = this.currentConfirmedText + this.previousTentativeText;
            const serverFinalText = newConfirmedText || "";

            let finalText = "";
            if (serverFinalText.length >= localFinalText.length) {
                // サーバーの最終確定テキストを採用
                finalText = serverFinalText;
                this.currentHiraganaConfirmed = newHiraganaConfirmed || "";
            } else {
                // ローカルの確定+暫定を採用（サーバーのデータが不完全な場合）
                finalText = localFinalText;
                this.currentHiraganaConfirmed += this.previousHiraganaTentative;
            }

            // 最終的に追加されたテキストを履歴に記録
            if (finalText.length > this.currentConfirmedText.length) {
                const addedText = finalText.slice(this.currentConfirmedText.length);
                const timestamp = this.sessionStartTime
                    ? (Date.now() - this.sessionStartTime) / 1000
                    : 0;

                const addedTranslation = "";

                // ひらがな正規化テキストの追加分を取得
                let addedHiragana = "";
                const localHiraganaFinal = this.currentHiraganaConfirmed + this.previousHiraganaTentative;

                if (newHiraganaConfirmed && newHiraganaConfirmed.length > this.currentHiraganaConfirmed.length) {
                    // サーバーからひらがなデータがある場合
                    addedHiragana = newHiraganaConfirmed.slice(this.currentHiraganaConfirmed.length);
                } else if (localHiraganaFinal.length > this.currentHiraganaConfirmed.length) {
                    // サーバーからひらがなデータがない場合は、ローカルのデータを使う
                    addedHiragana = localHiraganaFinal.slice(this.currentHiraganaConfirmed.length);
                }

                this.transcriptionHistory.push({
                    timestamp: timestamp,
                    text: addedText.trim(),
                    hiragana: addedHiragana.trim(),
                    translation: addedTranslation.trim()
                });

                console.log(`📝 最終履歴記録: [${timestamp.toFixed(1)}s] ${addedText.trim()}`);
            }

            this.currentConfirmedText = finalText;

            // テキストエリアを更新（確定のみ）
            this._updateTranscriptionDisplay(this.currentConfirmedText);
            this.previousTentativeText = "";
            this.previousHiraganaTentative = "";
            this.previousConfirmedText = this.currentConfirmedText;

            // ひらがな表示を更新
            this._updateHiraganaDisplay(this.currentHiraganaConfirmed);

            // 翻訳結果を表示
            if (this.translationText && newConfirmedTranslation) {
                this.translationText.classList.remove("processing");
                this.translationText.textContent = newConfirmedTranslation;
                console.log("✅ 翻訳完了");
                if (this.translationTextMobile) {
                    this.translationTextMobile.textContent = newConfirmedTranslation;
                }
            }

            return;
        }

        // 確定テキストが更新された場合（追記のみ、減少は無視）
        if (newConfirmedText && newConfirmedText.length > this.currentConfirmedText.length) {
            // デバッグログ: currentConfirmedTextの値を確認
            console.log("🔍 確定テキスト計算:");
            console.log("  this.currentConfirmedText.length:", this.currentConfirmedText.length);
            console.log("  newConfirmedText.length:", newConfirmedText.length);
            console.log("  this.currentConfirmedText (先頭50文字):", this.currentConfirmedText.slice(0, 50) || "(空)");

            // タイムスタンプ付きで履歴に記録
            const addedText = newConfirmedText.slice(this.currentConfirmedText.length);
            console.log("✅ 確定テキスト追加:", addedText.trim());
            const timestamp = this.sessionStartTime
                ? (Date.now() - this.sessionStartTime) / 1000
                : 0;

            const addedTranslation = "";

            const addedHiragana = newHiraganaConfirmed
                ? newHiraganaConfirmed.slice(this.currentHiraganaConfirmed.length)
                : "";

            this.transcriptionHistory.push({
                timestamp: timestamp,
                text: addedText.trim(),
                hiragana: addedHiragana.trim(),
                translation: addedTranslation.trim()
            });

            console.log(`📝 履歴記録: [${timestamp.toFixed(1)}s] ${addedText.trim()}`);

            // 確定テキストを保存・表示（追記のみ）
            this.currentConfirmedText = newConfirmedText;
            this.currentHiraganaConfirmed = newHiraganaConfirmed;

            // デバッグログ: タイピングアニメーションの引数を確認
            console.log("🔍 タイピングアニメーション:");
            console.log("  previousConfirmedText (先頭50文字):", this.previousConfirmedText?.slice(0, 50) || "(なし)");
            console.log("  newConfirmedText (先頭50文字):", newConfirmedText?.slice(0, 50) || "(なし)");
            console.log("  addedText (先頭50文字):", addedText?.slice(0, 50) || "(なし)");

            // テキストエリアを更新（確定テキスト追記アニメーション）
            this._updateTranscriptionDisplay(newConfirmedText, true, this.previousConfirmedText);

            this.previousConfirmedText = newConfirmedText;
            this.previousHiraganaConfirmed = newHiraganaConfirmed;
        } else if (newConfirmedText && newConfirmedText.length < this.currentConfirmedText.length) {
            // 確定テキストが減少した場合は無視（ログのみ）
            console.warn("⚠️ 確定テキスト減少を無視:", newConfirmedText.length, "<", this.currentConfirmedText.length);
        }

        // 暫定テキスト（内部管理のみ、表示しない）
        if (newTentativeText !== this.previousTentativeText) {
            console.log("⏳ 暫定テキスト:", newTentativeText);
            this.previousTentativeText = newTentativeText;
        }

        // ひらがな暫定テキストの内部保持
        if (newHiraganaTentative !== this.previousHiraganaTentative) {
            this.previousHiraganaTentative = newHiraganaTentative;
        }



    }

    /**
     * タイピングアニメーションをキャンセル
     */
    _cancelTypingAnimations() {
        this.typingTimers.forEach((timer) => clearTimeout(timer));
        this.typingTimers = [];
    }

    /**
     * 文字起こしテキストエリアを更新（確定テキストのみ表示）
     *
     * @param {string} confirmed - 確定テキスト
     * @param {boolean} animate - タイピングアニメーションで表示するか
     * @param {string} oldConfirmed - アニメーション前の確定テキスト
     */
    _updateTranscriptionDisplay(confirmed, animate = false, oldConfirmed = "") {
        if (animate && confirmed.startsWith(oldConfirmed)) {
            const additionalText = confirmed.slice(oldConfirmed.length);
            let currentConfirmed = oldConfirmed;
            let currentIndex = 0;

            const typeNextChar = () => {
                if (currentIndex < additionalText.length) {
                    currentConfirmed += additionalText[currentIndex];
                    currentIndex++;
                    this.transcriptionText.textContent = currentConfirmed;
                    this.transcriptionText.scrollTop = this.transcriptionText.scrollHeight;
                    const timer = setTimeout(typeNextChar, 50);
                    this.typingTimers.push(timer);
                }
            };

            this.transcriptionText.textContent = oldConfirmed;
            typeNextChar();
        } else {
            this.transcriptionText.textContent = confirmed;
            this.transcriptionText.scrollTop = this.transcriptionText.scrollHeight;
        }
    }

    /**
     * テキストをタイピングアニメーションで表示
     *
     * @param {HTMLElement} element - 対象要素
     * @param {string} oldText - 既存のテキスト
     * @param {string} newText - 新しいテキスト
     * @param {number} interval - 1文字あたりの表示間隔（ミリ秒）
     */
    _typeText(element, oldText, newText, interval = 30) {
        // 既存のテキストで始まっている場合は、差分だけを追加
        if (newText.startsWith(oldText)) {
            const additionalText = newText.slice(oldText.length);
            let currentIndex = 0;

            const typeNextChar = () => {
                if (currentIndex < additionalText.length) {
                    element.textContent += additionalText[currentIndex];
                    currentIndex++;
                    const timer = setTimeout(typeNextChar, interval);
                    this.typingTimers.push(timer);
                }
            };

            element.textContent = oldText;
            typeNextChar();
        } else {
            // 全く異なるテキストの場合は、一度にすべて表示
            element.textContent = newText;
        }
    }

    /**
     * ひらがな表示を更新（確定テキストのみ表示）
     *
     * @param {string} confirmedText - 確定テキスト
     */
    _updateHiraganaDisplay(confirmedText) {
        this.hiraganaText.classList.remove("processing");
        this.hiraganaText.textContent = confirmedText;
        this.hiraganaText.scrollTop = this.hiraganaText.scrollHeight;
        if (this.hiraganaTextMobile) {
            this.hiraganaTextMobile.textContent = confirmedText;
            this.hiraganaTextMobile.scrollTop = this.hiraganaTextMobile.scrollHeight;
        }
    }

    /**
     * ボタンの状態を設定
     *
     * @param {boolean} isRecording - 録音中かどうか
     */
    setButtonsState(isRecording) {
        const icon = this.startButton.querySelector(".material-symbols-outlined");

        if (isRecording) {
            // 録音中：赤いstopボタン
            this.startButton.classList.add("recording");
            if (icon) icon.textContent = "stop";
            this.startButton.disabled = false;
            if (this.downloadButton) this.downloadButton.disabled = true;
        } else {
            // 待機中：青いplayボタン
            this.startButton.classList.remove("recording");
            if (icon) icon.textContent = "play_arrow";
            this.startButton.disabled = false;
        }

        // ソースエリアのフェードアウト/イン
        document.body.classList.toggle("recording", isRecording);
    }

    /**
     * デバイス一覧を取得して表示
     */
    async populateDeviceSelector() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const audioInputs = devices.filter((device) => device.kind === "audioinput");

            this.deviceSelector.innerHTML = "";
            audioInputs.forEach((device, index) => {
                const option = document.createElement("option");
                option.value = device.deviceId;
                option.textContent = device.label || `マイク ${index + 1}`;
                this.deviceSelector.appendChild(option);
            });
        } catch (error) {
            console.error("デバイス一覧取得エラー:", error);
        }
    }

    /**
     * エラーメッセージを表示
     *
     * @param {string} message - エラーメッセージ
     */
    showError(message) {
        this.setStatus("error");
        this.showToast(message, "error", 5000);
    }



    /**
     * トースト通知を表示
     *
     * @param {string} message - 表示メッセージ
     * @param {string} type - タイプ (info, success, error, warning)
     * @param {number} duration - 表示時間（ミリ秒、デフォルト: 3000）
     */
    showToast(message, type = "info", duration = 3000) {
        // トースト要素を作成
        const toast = document.createElement("div");
        toast.className = `toast ${type}`;

        // アイコンを設定
        const iconMap = {
            info: "ℹ️",
            success: "✅",
            error: "❌",
            warning: "⚠️",
        };

        toast.innerHTML = `
            <span class="toast-icon">${iconMap[type] || "ℹ️"}</span>
            <span class="toast-message">${this._escapeHtml(message)}</span>
        `;

        // コンテナに追加
        this.toastContainer.appendChild(toast);

        // 自動で消去
        setTimeout(() => {
            toast.classList.add("fade-out");
            setTimeout(() => {
                if (toast.parentNode) {
                    toast.parentNode.removeChild(toast);
                }
            }, 300); // アニメーション完了を待つ
        }, duration);
    }

    /**
     * HTMLエスケープ
     *
     * @param {string} text - エスケープするテキスト
     * @returns {string} - エスケープ済みテキスト
     */
    _escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    /**
     * ひらがなセクションの表示/非表示を切り替え
     *
     * @param {boolean} enabled - 表示するかどうか
     */
    toggleHiraganaSection(enabled) {
        if (this.hiraganaSection) {
            this.hiraganaSection.classList.toggle("inactive", !enabled);
        }
    }

    /**
     * 翻訳セクションの表示/非表示を切り替え
     *
     * @param {boolean} enabled - 表示するかどうか
     */
    toggleTranslationSection(enabled) {
        if (this.translationSection) {
            this.translationSection.classList.toggle("inactive", !enabled);
        }
    }

    /**
     * 要約セクションの表示/非表示を切り替え
     *
     * @param {boolean} enabled - 表示するかどうか
     */
    toggleSummarySection(enabled) {
        // デスクトップ: カードは常時表示（トグルは自動要約の有効/無効のみ制御）
        // モバイル: タブの表示/非表示は main.js で制御
    }

    /**
     * すべてのテキスト表示をクリア
     * 新しい録音セッション開始時に呼び出される
     */
    clearAllText() {
        // テキスト表示をクリア
        this.transcriptionText.innerHTML = "";
        this.hiraganaText.classList.remove("processing");
        this.hiraganaText.innerHTML = "";

        if (this.hiraganaTextMobile) { this.hiraganaTextMobile.innerHTML = ""; }
        if (this.translationTextMobile) { this.translationTextMobile.textContent = ""; }
        if (this.translationText) {
            this.translationText.classList.remove("processing");
            this.translationText.textContent = "";
        }



        // 内部状態をリセット
        this.previousConfirmedText = "";
        this.previousTentativeText = "";
        this.previousHiraganaConfirmed = "";
        this.previousHiraganaTentative = "";


        this.currentConfirmedText = "";
        this.currentHiraganaConfirmed = "";

        // 要約リセット（カードは常時表示）
        this.finalSummary = "";
        if (this.summaryText) this.summaryText.textContent = "";

        // セッションデータをリセット
        this.sessionStartTime = null;
        this.transcriptionHistory = [];
        this.finalHiragana = "";
        this.finalTranslation = "";

        // タイピングアニメーションをキャンセル
        this._cancelTypingAnimations();

        console.log("✨ すべてのテキスト表示をクリアしました");
    }

    /**
     * タイムスタンプをフォーマット
     *
     * @param {number} seconds - 秒数
     * @returns {string} - [HH:MM:SS] 形式の文字列
     */
    _formatTimestamp(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);

        const hh = String(hours).padStart(2, "0");
        const mm = String(minutes).padStart(2, "0");
        const ss = String(secs).padStart(2, "0");

        return `[${hh}:${mm}:${ss}]`;
    }

    /**
     * メタデータヘッダーを生成
     *
     * @param {string} inputSource - 入力ソース
     * @param {Object} processingOptions - 処理オプション
     * @returns {string} - ヘッダー文字列
     */
    _generateMetadataHeader(inputSource, processingOptions) {
        const now = new Date();
        const dateStr = now.toLocaleString("ja-JP", {
            year: "numeric",
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit"
        });

        const sourceLabels = {
            microphone: "マイク入力",
            video: "動画ファイル",
            tab: "タブ共有"
        };

        const hiraganaStatus = processingOptions.enableHiragana ? "ON" : "OFF";
        const translationStatus = processingOptions.enableTranslation ? "ON" : "OFF";

        return `===========================
文字起こし結果
日時: ${dateStr}
入力ソース: ${sourceLabels[inputSource] || inputSource}
処理: ひらがな正規化=${hiraganaStatus}, 翻訳=${translationStatus}
===========================

`;
    }

    /**
     * ファイル名を生成
     *
     * @returns {string} - transcript_YYYYMMDD_HHMMSS.txt 形式のファイル名
     */
    _generateFileName() {
        const now = new Date();
        const year = now.getFullYear();
        const month = String(now.getMonth() + 1).padStart(2, "0");
        const day = String(now.getDate()).padStart(2, "0");
        const hours = String(now.getHours()).padStart(2, "0");
        const minutes = String(now.getMinutes()).padStart(2, "0");
        const seconds = String(now.getSeconds()).padStart(2, "0");

        return `transcript_${year}${month}${day}_${hours}${minutes}${seconds}.txt`;
    }

    /**
     * 文字起こし結果のテキストを生成
     *
     * @param {string} inputSource - 入力ソース
     * @param {Object} processingOptions - 処理オプション
     * @returns {string} - ファイル内容
     */
    generateTranscriptText(inputSource, processingOptions) {
        let content = this._generateMetadataHeader(inputSource, processingOptions);

        // 履歴データから本文を生成（文字起こしのみ）
        for (const entry of this.transcriptionHistory) {
            const timestamp = this._formatTimestamp(entry.timestamp);
            content += `${timestamp} ${entry.text}\n`;
        }

        // ひらがな正規化セクション（セッション終了時に一括処理された全体テキスト）
        if (processingOptions.enableHiragana && this.finalHiragana) {
            content += "\n--- ひらがな正規化 ---\n";
            content += `${this.finalHiragana}\n`;
        }

        // 翻訳セクション（セッション終了時に一括処理された全体テキスト）
        if (processingOptions.enableTranslation && this.finalTranslation) {
            content += "\n--- 翻訳 ---\n";
            content += `${this.finalTranslation}\n`;
        }

        // 要約セクション
        if (this.finalSummary) {
            content += "\n--- 要約 ---\n";
            content += `${this.finalSummary}\n`;
        }

        return content;
    }

    /**
     * セッション終了時の最終ひらがな・翻訳を保存
     *
     * @param {string} hiragana - ひらがな全体テキスト
     * @param {string} translation - 翻訳全体テキスト
     */
    setFinalResults(hiragana, translation) {
        this.finalHiragana = hiragana || "";
        this.finalTranslation = translation || "";
        console.log(`📝 最終結果を保存: ひらがな=${this.finalHiragana.length}文字, 翻訳=${this.finalTranslation.length}文字`);
    }

    /**
     * 文字起こし結果をダウンロード
     *
     * @param {string} inputSource - 入力ソース
     * @param {Object} processingOptions - 処理オプション
     */
    downloadTranscript(inputSource, processingOptions) {
        if (this.transcriptionHistory.length === 0) {
            this.showToast("ダウンロードするデータがありません", "warning");
            return;
        }

        const textContent = this.generateTranscriptText(inputSource, processingOptions);

        // UTF-8 BOM付きでBlob生成（Excel対応）
        const bom = new Uint8Array([0xEF, 0xBB, 0xBF]);
        const blob = new Blob([bom, textContent], { type: "text/plain;charset=utf-8" });

        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = this._generateFileName();

        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);

        this.showToast(`ファイルをダウンロードしました: ${link.download}`, "success");
        console.log("📥 ダウンロード完了:", link.download);
    }

    /**
     * トリミングインジケーターを表示
     */
    showTrimIndicator() {
        const indicator = document.getElementById("trim-indicator");
        if (indicator) {
            indicator.style.display = "flex";
        }
    }

    /**
     * トリミングインジケーターを非表示
     */
    hideTrimIndicator() {
        const indicator = document.getElementById("trim-indicator");
        if (indicator) {
            // フェードアウトアニメーション
            indicator.style.animation = "fadeOut 0.3s ease-in-out";
            setTimeout(() => {
                indicator.style.display = "none";
                indicator.style.animation = "fadeInOut 0.3s ease-in-out";
            }, 300);
        }
    }

    /**
     * 確定テキストを取得
     *
     * @returns {string} - 現在の確定テキスト
     */
    getConfirmedText() {
        return this.currentConfirmedText || "";
    }

    /**
     * 要約結果を表示
     *
     * @param {string} summary - 要約テキスト
     */
    showSummary(summary) {
        this.finalSummary = summary;
        if (this.summaryText) this.summaryText.textContent = summary;
        if (this.summaryLoading) this.summaryLoading.style.display = "none";
        // モバイル要約パネルにも反映
        const summaryTextMobile = document.getElementById("summary-text-mobile");
        if (summaryTextMobile) summaryTextMobile.textContent = summary;
        console.log("📝 要約を表示しました");
    }

    /**
     * 要約ローディング表示の切り替え
     *
     * @param {boolean} loading - ローディング中かどうか
     */
    showSummaryLoading(loading) {
        if (this.summaryLoading) {
            this.summaryLoading.style.display = loading ? "flex" : "none";
        }
        if (this.summaryText && loading) {
            this.summaryText.textContent = "";
        }
    }

    /**
     * 強制確定処理（タイムアウト時用）
     * 現在の暫定テキストを確定テキストに強制的に移行します。
     */
    forceFinalize() {
        console.log("⚠️ 強制確定処理を実行");

        // 暫定テキストが存在する場合のみ処理
        if (this.previousTentativeText) {
            // 暫定テキストを確定テキストに追加
            this.currentConfirmedText += this.previousTentativeText;
            this._updateTranscriptionDisplay(this.currentConfirmedText);

            // 履歴に記録
            const timestamp = this.sessionStartTime
                ? (Date.now() - this.sessionStartTime) / 1000
                : 0;

            this.transcriptionHistory.push({
                timestamp: timestamp,
                text: this.previousTentativeText.trim(),
                hiragana: this.previousHiraganaTentative.trim(),
                translation: ""
            });

            console.log(`📝 強制確定履歴記録: [${timestamp.toFixed(1)}s] ${this.previousTentativeText.trim()}`);

            // 暫定テキストをクリア
            this.previousTentativeText = "";
            this.previousConfirmedText = this.currentConfirmedText;

            console.log("✅ 強制確定完了: 暫定→確定移行");
        }

        // ひらがなの暫定を確定に移行
        if (this.previousHiraganaTentative) {
            this.currentHiraganaConfirmed += this.previousHiraganaTentative;
            this._updateHiraganaDisplay(this.currentHiraganaConfirmed);
            this.previousHiraganaTentative = "";
        }


    }
}
