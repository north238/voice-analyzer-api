/**
 * UIController - UI要素の更新管理
 *
 * DOM要素の参照を保持し、表示内容を更新します。
 */
class UIController {
    constructor() {
        // DOM要素の参照
        this.startButton = document.getElementById("start-button");
        this.stopButton = document.getElementById("stop-button");
        this.statusText = document.getElementById("status-text");
        this.volumeMeter = document.getElementById("volume-meter");
        this.volumeBar = document.getElementById("volume-bar");

        this.confirmedText = document.getElementById("confirmed-text");
        this.tentativeText = document.getElementById("tentative-text");
        this.hiraganaText = document.getElementById("hiragana-text");

        this.confirmedTranslation = document.getElementById("confirmed-translation");
        this.tentativeTranslation = document.getElementById("tentative-translation");
        this.hiraganaSection = document.querySelector(".hiragana-results");
        this.translationSection = document.getElementById("translation-section");

        this.performanceInfo = document.getElementById("performance-info");
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
     * 文字起こし結果を更新
     *
     * @param {Object} data - 文字起こしデータ
     */
    updateTranscription(data) {
        console.log("🖥️ UI更新:", data);

        const transcription = data.transcription || {};
        const hiragana = data.hiragana || {};

        const newConfirmedText = transcription.confirmed || "";
        const newTentativeText = transcription.tentative || "";
        const newHiraganaConfirmed = hiragana.confirmed || "";
        const newHiraganaTentative = hiragana.tentative || "";

        // 既存のタイピングアニメーションをキャンセル
        this._cancelTypingAnimations();

        // セッション終了時（暫定が空で確定が来た場合）は、最終確定テキストを反映
        const isSessionEnd = !newTentativeText && this.previousTentativeText;
        if (isSessionEnd) {
            console.log("🏁 セッション終了: 暫定テキストを確定に移行");

            // サーバーからの最終確定テキストと、ローカルの確定+暫定を比較して長い方を採用
            const localFinalText = this.currentConfirmedText + this.previousTentativeText;
            const serverFinalText = newConfirmedText || "";

            if (serverFinalText.length >= localFinalText.length) {
                // サーバーの最終確定テキストを採用
                this.currentConfirmedText = serverFinalText;
                this.currentHiraganaConfirmed = newHiraganaConfirmed || "";
            } else {
                // ローカルの確定+暫定を採用（サーバーのデータが不完全な場合）
                this.currentConfirmedText = localFinalText;
                this.currentHiraganaConfirmed += this.previousHiraganaTentative;
            }

            // 確定テキスト欄を更新
            this.confirmedText.textContent = this.currentConfirmedText;

            // 暫定テキストをクリア
            this.tentativeText.textContent = "";
            this.previousTentativeText = "";
            this.previousHiraganaTentative = "";
            this.previousConfirmedText = this.currentConfirmedText;

            // ひらがな表示を更新
            this._updateHiraganaDisplay("", this.currentHiraganaConfirmed);

            // 翻訳の暫定→確定移行
            const translation = data.translation || {};
            const newConfirmedTranslation = translation.confirmed || "";
            const newTentativeTranslation = translation.tentative || "";

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
            console.log("✅ 確定テキスト追加:", newConfirmedText);

            // 確定テキストを保存・表示（追記のみ）
            this.currentConfirmedText = newConfirmedText;
            this.currentHiraganaConfirmed = newHiraganaConfirmed;

            // タイピングアニメーションで表示
            this._typeText(
                this.confirmedText,
                this.previousConfirmedText,
                newConfirmedText,
                50,
            );

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
        const translation = data.translation || {};
        const newConfirmedTranslation = translation.confirmed || "";
        const newTentativeTranslation = translation.tentative || "";

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

        // パフォーマンス情報
        const perf = data.performance || {};
        this.performanceInfo.innerHTML = `
            <div>文字起こし: ${(perf.transcription_time || 0).toFixed(2)}秒</div>
            <div>累積音声: ${(perf.accumulated_audio_seconds || 0).toFixed(1)}秒</div>
            <div>合計: ${(perf.total_time || 0).toFixed(2)}秒</div>
        `;
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
        this.startButton.disabled = isRecording;
        this.stopButton.disabled = !isRecording;
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
            this.hiraganaSection.style.display = enabled ? "block" : "none";
        }
    }

    /**
     * 翻訳セクションの表示/非表示を切り替え
     *
     * @param {boolean} enabled - 表示するかどうか
     */
    toggleTranslationSection(enabled) {
        if (this.translationSection) {
            this.translationSection.style.display = enabled ? "block" : "none";
        }
    }

    /**
     * すべてのテキスト表示をクリア
     * 新しい録音セッション開始時に呼び出される
     */
    clearAllText() {
        // テキスト表示をクリア
        this.confirmedText.textContent = "";
        this.tentativeText.textContent = "";
        this.hiraganaText.innerHTML = "";

        if (this.confirmedTranslation) {
            this.confirmedTranslation.textContent = "";
        }
        if (this.tentativeTranslation) {
            this.tentativeTranslation.textContent = "";
        }

        // パフォーマンス情報をクリア
        this.performanceInfo.innerHTML = "";

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

        // タイピングアニメーションをキャンセル
        this._cancelTypingAnimations();

        console.log("✨ すべてのテキスト表示をクリアしました");
    }
}
