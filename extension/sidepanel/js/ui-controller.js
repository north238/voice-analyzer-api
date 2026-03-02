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
        this.statusText = document.getElementById("status-text");
        this.volumeMeter = document.getElementById("volume-meter");
        this.volumeBar = document.getElementById("volume-bar");

        this.confirmedText = document.getElementById("confirmed-text");
        this.tentativeText = document.getElementById("tentative-text");
        this.hiraganaText = document.getElementById("hiragana-text");

        this.confirmedTranslation = document.getElementById("confirmed-translation");
        this.tentativeTranslation = document.getElementById("tentative-translation");
        // card-body要素（inactive切り替え用）
        this.hiraganaCardBody = document.getElementById("hiragana-pane");
        this.translationCardBody = document.getElementById("translation-pane");

        // 要約関連
        this.summaryCard = document.getElementById("summary-card");
        this.summaryText = document.getElementById("summary-text");
        this.summaryLoading = document.getElementById("summary-loading");

        this.deviceSelector = document.getElementById("device-selector");
        this.toastContainer = document.getElementById("toast-container");

        // タイピングアニメーション用の状態管理
        this.previousConfirmedText = "";
        this.previousTentativeText = "";
        this.previousHiraganaConfirmed = "";
        this.previousHiraganaTentative = "";
        this.previousConfirmedTranslation = "";
        this.previousTentativeTranslation = "";
        this.typingTimers = [];

        // 現在の確定テキスト（累積）
        this.currentConfirmedText = "";
        this.currentHiraganaConfirmed = "";
        this.currentConfirmedTranslation = "";

        // セッションデータ（ダウンロード用）
        this.sessionStartTime = null;
        this.transcriptionHistory = [];
        this.finalHiragana = "";
        this.finalTranslation = "";
        this.finalSummary = "";
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
        console.log("📝 セッション開始時刻を記録しました");
    }

    /**
     * ステータスメッセージを設定
     *
     * @param {string} message - 表示メッセージ
     * @param {string} type - ステータスタイプ (info, success, error, recording)
     */
    setStatus(message, type = "info") {
        this.statusText.textContent = message;
        this.statusText.className = `status ${type}`;
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
     * 表示用タイムスタンプをフォーマット（MM:SS形式、1h超はH:MM:SS）
     *
     * @param {number} seconds - 秒数
     * @returns {string} - [MM:SS] または [H:MM:SS] 形式の文字列
     */
    _formatDisplayTimestamp(seconds) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = Math.floor(seconds % 60);
        const mm = String(minutes).padStart(2, "0");
        const ss = String(secs).padStart(2, "0");
        return hours > 0 ? `[${hours}:${mm}:${ss}]` : `[${mm}:${ss}]`;
    }

    /**
     * 確定テキストブロックを追記
     *
     * @param {string} addedText - 追加されたテキスト
     * @param {number} timestamp - タイムスタンプ（秒）
     */
    _appendConfirmedBlock(addedText, timestamp) {
        const ts = this._formatDisplayTimestamp(timestamp);
        const block = document.createElement("div");
        block.className = "confirmed-block";
        block.innerHTML = `<span class="timestamp">${ts}</span> ${this._escapeHtml(addedText.trim())}`;
        this.confirmedText.appendChild(block);
        this.confirmedText.scrollTop = this.confirmedText.scrollHeight;
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
        const newConfirmedTranslation = translation.confirmed || "";
        const newTentativeTranslation = translation.tentative || "";

        // デバッグログ: WebSocket受信データを確認
        if (newConfirmedText) {
            console.log("🔍 WebSocket受信データ:");
            console.log("  confirmed.length:", newConfirmedText.length);
            console.log("  confirmed (先頭100文字):", newConfirmedText.slice(0, 100));
            console.log("  confirmed (末尾100文字):", newConfirmedText.slice(-100));
        }

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

            // 最終的に追加されたテキストを履歴に記録し、タイムスタンプ付きブロックで表示
            if (finalText.length > this.currentConfirmedText.length) {
                const addedText = finalText.slice(this.currentConfirmedText.length);
                const timestamp = this.sessionStartTime
                    ? (Date.now() - this.sessionStartTime) / 1000
                    : 0;

                const addedTranslation = newConfirmedTranslation
                    ? newConfirmedTranslation.slice(this.currentConfirmedTranslation.length)
                    : "";

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

                // タイムスタンプ付きブロックで表示
                this._appendConfirmedBlock(addedText, timestamp);
            }

            this.currentConfirmedText = finalText;

            // 暫定テキストをクリア
            this.tentativeText.textContent = "";
            this.previousTentativeText = "";
            this.previousHiraganaTentative = "";
            this.previousConfirmedText = this.currentConfirmedText;

            // ひらがな表示を更新
            this._updateHiraganaDisplay("", this.currentHiraganaConfirmed);

            // 翻訳の暫定→確定移行
            if (this.confirmedTranslation && this.tentativeTranslation) {
                // サーバーからの最終確定翻訳と、ローカルの確定+暫定を比較
                const localFinalTranslation = this.currentConfirmedTranslation + this.previousTentativeTranslation;
                const serverFinalTranslation = newConfirmedTranslation || "";

                if (serverFinalTranslation.length >= localFinalTranslation.length) {
                    // サーバーの最終確定翻訳を採用
                    this.currentConfirmedTranslation = serverFinalTranslation;
                } else {
                    // ローカルの確定+暫定を採用
                    this.currentConfirmedTranslation = localFinalTranslation;
                }

                // 確定翻訳欄を更新
                this.confirmedTranslation.textContent = this.currentConfirmedTranslation;

                // 暫定翻訳をクリア
                this.tentativeTranslation.textContent = "";
                this.previousTentativeTranslation = "";
                this.previousConfirmedTranslation = this.currentConfirmedTranslation;

                console.log("✅ 翻訳の暫定→確定移行完了");
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

            const addedTranslation = newConfirmedTranslation
                ? newConfirmedTranslation.slice(this.currentConfirmedTranslation.length)
                : "";

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

            // 確定テキストを保存
            this.currentConfirmedText = newConfirmedText;
            this.currentHiraganaConfirmed = newHiraganaConfirmed;

            // タイムスタンプ付きブロックで表示
            this._appendConfirmedBlock(addedText, timestamp);

            this.previousConfirmedText = newConfirmedText;
            this.previousHiraganaConfirmed = newHiraganaConfirmed;
        } else if (newConfirmedText && newConfirmedText.length < this.currentConfirmedText.length) {
            // 確定テキストが減少した場合は無視（ログのみ）
            console.warn("⚠️ 確定テキスト減少を無視:", newConfirmedText.length, "<", this.currentConfirmedText.length);
        }

        // 暫定テキスト（タイピングアニメーション）
        if (newTentativeText !== this.previousTentativeText) {
            console.log("⏳ 暫定テキスト:", newTentativeText);
            this._typeText(
                this.tentativeText,
                this.previousTentativeText,
                newTentativeText,
                50,
            );
            this.previousTentativeText = newTentativeText;
        }

        // ひらがな表示の更新
        if (newHiraganaConfirmed !== this.previousHiraganaConfirmed ||
            newHiraganaTentative !== this.previousHiraganaTentative) {
            this._updateHiraganaDisplay(newHiraganaTentative, newHiraganaConfirmed);
            this.previousHiraganaTentative = newHiraganaTentative;
        }

        // 翻訳結果の更新
        if (this.confirmedTranslation && this.tentativeTranslation) {
            // 確定翻訳（追記のみ）
            if (newConfirmedTranslation && newConfirmedTranslation.length > this.currentConfirmedTranslation.length) {
                this.currentConfirmedTranslation = newConfirmedTranslation;
                this._typeText(
                    this.confirmedTranslation,
                    this.previousConfirmedTranslation,
                    newConfirmedTranslation,
                    50
                );
                this.previousConfirmedTranslation = newConfirmedTranslation;
            }

            // 暫定翻訳
            if (newTentativeTranslation !== this.previousTentativeTranslation) {
                this._typeText(
                    this.tentativeTranslation,
                    this.previousTentativeTranslation,
                    newTentativeTranslation,
                    50
                );
                this.previousTentativeTranslation = newTentativeTranslation;
            }
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
     * ひらがなテキストをタイピングアニメーションで表示
     *
     * @param {string} oldFullText - 既存の全テキスト
     * @param {string} newConfirmed - 新しい確定テキスト
     * @param {string} newTentative - 新しい暫定テキスト
     * @param {number} interval - 1文字あたりの表示間隔（ミリ秒）
     */
    _typeHiragana(oldFullText, newConfirmed, newTentative, interval = 30) {
        const newFullText = newConfirmed + newTentative;

        // 既存のテキストで始まっている場合は、差分だけを追加
        if (newFullText.startsWith(oldFullText)) {
            const additionalText = newFullText.slice(oldFullText.length);
            let currentIndex = 0;
            let currentDisplayedText = oldFullText;

            const typeNextChar = () => {
                if (currentIndex < additionalText.length) {
                    currentDisplayedText += additionalText[currentIndex];
                    currentIndex++;

                    // 確定部分と暫定部分を分離して表示
                    const displayedConfirmed = currentDisplayedText.slice(0, newConfirmed.length);
                    const displayedTentative = currentDisplayedText.slice(newConfirmed.length);

                    this.hiraganaText.innerHTML =
                        `<span class="confirmed">${this._escapeHtml(displayedConfirmed)}</span>` +
                        `<span class="tentative">${this._escapeHtml(displayedTentative)}</span>`;

                    const timer = setTimeout(typeNextChar, interval);
                    this.typingTimers.push(timer);
                }
            };

            // 初期表示
            const displayedConfirmed = oldFullText.slice(0, Math.min(oldFullText.length, newConfirmed.length));
            const displayedTentative = oldFullText.slice(Math.min(oldFullText.length, newConfirmed.length));
            this.hiraganaText.innerHTML =
                `<span class="confirmed">${this._escapeHtml(displayedConfirmed)}</span>` +
                `<span class="tentative">${this._escapeHtml(displayedTentative)}</span>`;

            typeNextChar();
        } else {
            // 全く異なるテキストの場合は、一度にすべて表示
            this.hiraganaText.innerHTML =
                `<span class="confirmed">${this._escapeHtml(newConfirmed)}</span>` +
                `<span class="tentative">${this._escapeHtml(newTentative)}</span>`;
        }
    }

    /**
     * ひらがな表示を更新（確定 + 暫定）
     *
     * @param {string} tentativeText - 暫定テキスト
     * @param {string} confirmedText - 確定テキスト（省略時は現在の値を使用）
     */
    _updateHiraganaDisplay(tentativeText, confirmedText = null) {
        const confirmed = confirmedText !== null ? confirmedText : this.currentHiraganaConfirmed;

        // 確定テキスト
        const confirmedHtml = confirmed
            ? `<span class="confirmed">${this._escapeHtml(confirmed)}</span>`
            : "";

        // 暫定テキスト
        const tentativeHtml = tentativeText
            ? `<span class="tentative">${this._escapeHtml(tentativeText)}</span>`
            : "";

        this.hiraganaText.innerHTML = confirmedHtml + tentativeHtml;
    }

    /**
     * ボタンの状態を設定
     *
     * @param {boolean} isRecording - 録音中かどうか
     */
    setButtonsState(isRecording) {
        const icon = this.startButton.querySelector(".material-symbols-outlined");

        if (isRecording) {
            document.body.classList.add("recording");
            // 録音中：赤いstopボタン
            this.startButton.className = "btn-circle btn-recording";
            if (icon) icon.textContent = "stop";
            this.startButton.disabled = false;
            if (this.downloadButton) this.downloadButton.disabled = true;
        } else {
            document.body.classList.remove("recording");
            // 待機中：青いplayボタン
            this.startButton.className = "btn-circle btn-primary";
            if (icon) icon.textContent = "play_arrow";
            this.startButton.disabled = false;
        }
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
        this.setStatus(`エラー: ${message}`, "error");
        this.showToast(message, "error", 5000);
    }

    /**
     * 状態インジケーターを設定
     *
     * @param {string} state - 状態 ('connecting' | 'recording' | 'processing' | 'idle')
     * @param {string} label - 表示テキスト（省略時は非表示）
     */
    setStateIndicator(state, label = "") {
        const indicator = document.getElementById("state-indicator");
        const labelEl = document.getElementById("state-label");
        if (!indicator || !labelEl) return;

        indicator.className = "state-indicator";

        if (!state || state === "idle") {
            indicator.classList.add("hidden");
            return;
        }

        indicator.classList.add(state);
        labelEl.textContent = label;
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
     * ひらがなセクションの表示/非表示を切り替え（opacity方式）
     *
     * @param {boolean} enabled - 有効にするかどうか
     */
    toggleHiraganaSection(enabled) {
        if (this.hiraganaCardBody) {
            if (enabled) {
                this.hiraganaCardBody.classList.remove("inactive");
            } else {
                this.hiraganaCardBody.classList.add("inactive");
            }
        }
    }

    /**
     * 翻訳セクションの表示/非表示を切り替え（opacity方式）
     *
     * @param {boolean} enabled - 有効にするかどうか
     */
    toggleTranslationSection(enabled) {
        if (this.translationCardBody) {
            if (enabled) {
                this.translationCardBody.classList.remove("inactive");
            } else {
                this.translationCardBody.classList.add("inactive");
            }
        }
    }

    /**
     * 確定テキストを取得
     *
     * @returns {string} - 現在の確定テキスト
     */
    getConfirmedText() {
        return this.currentConfirmedText;
    }

    /**
     * 要約を表示
     *
     * @param {string} summary - 要約テキスト
     */
    showSummary(summary) {
        if (this.summaryCard) {
            this.summaryCard.style.display = "";
            this.summaryCard.classList.remove("summary-loading-border");
        }
        if (this.summaryText) {
            this.summaryText.textContent = summary;
        }
        if (this.summaryLoading) {
            this.summaryLoading.style.display = "none";
        }
        this.finalSummary = summary;
        console.log(`📋 要約表示: ${summary.length}文字`);
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
     * すべてのテキスト表示をクリア
     * 新しい録音セッション開始時に呼び出される
     */
    clearAllText() {
        // テキスト表示をクリア（ブロック要素を含むためinnerHTMLでクリア）
        this.confirmedText.innerHTML = "";
        this.tentativeText.textContent = "";
        this.hiraganaText.innerHTML = "";

        if (this.confirmedTranslation) {
            this.confirmedTranslation.textContent = "";
        }
        if (this.tentativeTranslation) {
            this.tentativeTranslation.textContent = "";
        }

        // 要約をクリア
        if (this.summaryCard) {
            this.summaryCard.style.display = "none";
        }
        if (this.summaryText) {
            this.summaryText.textContent = "";
        }
        if (this.summaryLoading) {
            this.summaryLoading.style.display = "none";
        }
        const summaryButton = document.getElementById("summary-button");
        if (summaryButton) {
            summaryButton.disabled = true;
        }

        // 内部状態をリセット
        this.previousConfirmedText = "";
        this.previousTentativeText = "";
        this.previousHiraganaConfirmed = "";
        this.previousHiraganaTentative = "";
        this.previousConfirmedTranslation = "";
        this.previousTentativeTranslation = "";

        this.currentConfirmedText = "";
        this.currentHiraganaConfirmed = "";
        this.currentConfirmedTranslation = "";

        // セッションデータをリセット
        this.sessionStartTime = null;
        this.transcriptionHistory = [];
        this.finalHiragana = "";
        this.finalTranslation = "";
        this.finalSummary = "";

        // タイピングアニメーションをキャンセル
        this._cancelTypingAnimations();

        console.log("✨ すべてのテキスト表示をクリアしました");
    }

    /**
     * タイムスタンプをフォーマット（ダウンロード用 [HH:MM:SS] 形式）
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
     * 強制確定処理（タイムアウト時用）
     * 現在の暫定テキストを確定テキストに強制的に移行します。
     */
    forceFinalize() {
        console.log("⚠️ 強制確定処理を実行");

        // 暫定テキストが存在する場合のみ処理
        if (this.previousTentativeText) {
            // 暫定テキストを確定テキストに追加
            this.currentConfirmedText += this.previousTentativeText;

            // 履歴に記録
            const timestamp = this.sessionStartTime
                ? (Date.now() - this.sessionStartTime) / 1000
                : 0;

            this.transcriptionHistory.push({
                timestamp: timestamp,
                text: this.previousTentativeText.trim(),
                hiragana: this.previousHiraganaTentative.trim(),
                translation: this.previousTentativeTranslation.trim()
            });

            console.log(`📝 強制確定履歴記録: [${timestamp.toFixed(1)}s] ${this.previousTentativeText.trim()}`);

            // タイムスタンプ付きブロックで表示
            this._appendConfirmedBlock(this.previousTentativeText, timestamp);

            // 暫定テキストをクリア
            this.tentativeText.textContent = "";
            this.previousTentativeText = "";
            this.previousConfirmedText = this.currentConfirmedText;

            console.log("✅ 強制確定完了: 暫定→確定移行");
        }

        // ひらがなの暫定を確定に移行
        if (this.previousHiraganaTentative) {
            this.currentHiraganaConfirmed += this.previousHiraganaTentative;
            this._updateHiraganaDisplay("", this.currentHiraganaConfirmed);
            this.previousHiraganaTentative = "";
        }

        // 翻訳の暫定を確定に移行
        if (this.previousTentativeTranslation && this.confirmedTranslation && this.tentativeTranslation) {
            this.currentConfirmedTranslation += this.previousTentativeTranslation;
            this.confirmedTranslation.textContent = this.currentConfirmedTranslation;
            this.tentativeTranslation.textContent = "";
            this.previousTentativeTranslation = "";
        }
    }
}
