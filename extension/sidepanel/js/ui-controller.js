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
        this.downloadButton = document.getElementById("download-button");
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

        // セッションデータ（ダウンロード用）
        this.sessionStartTime = null;
        this.transcriptionHistory = [];
    }

    /**
     * セッション開始
     * セッション開始時刻を記録
     */
    startSession() {
        this.sessionStartTime = Date.now();
        this.transcriptionHistory = [];
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

            // 最終的に追加されたテキストを履歴に記録
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
            }

            this.currentConfirmedText = finalText;

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

            // 確定テキストを保存・表示（追記のみ）
            this.currentConfirmedText = newConfirmedText;
            this.currentHiraganaConfirmed = newHiraganaConfirmed;

            // デバッグログ: タイピングアニメーションの引数を確認
            console.log("🔍 タイピングアニメーション:");
            console.log("  previousConfirmedText (先頭50文字):", this.previousConfirmedText?.slice(0, 50) || "(なし)");
            console.log("  newConfirmedText (先頭50文字):", newConfirmedText?.slice(0, 50) || "(なし)");
            console.log("  addedText (先頭50文字):", addedText?.slice(0, 50) || "(なし)");

            // タイピングアニメーション + ハイライト効果で表示
            this._typeTextWithHighlight(
                this.confirmedText,
                this.previousConfirmedText,
                newConfirmedText,
                addedText,
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
        this._updatePerformanceInfo(perf);
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
     * テキストをタイピングアニメーション + ハイライト効果で表示
     *
     * @param {HTMLElement} element - 対象要素
     * @param {string} oldText - 既存のテキスト
     * @param {string} newText - 新しいテキスト
     * @param {string} addedText - 追加されたテキスト
     * @param {number} interval - 1文字あたりの表示間隔（ミリ秒）
     */
    _typeTextWithHighlight(element, oldText, newText, addedText, interval = 30) {
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

        // 録音中はダウンロードボタンを無効化
        if (isRecording && this.downloadButton) {
            this.downloadButton.disabled = true;
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
     * パフォーマンス情報を更新
     *
     * @param {Object} perf - パフォーマンスデータ
     */
    _updatePerformanceInfo(perf) {
        const transcriptionTime = perf.transcription_time || 0;
        const normalizationTime = perf.normalization_time || 0;
        const translationTime = perf.translation_time || 0;
        const totalTime = perf.total_time || 0;
        const recordingTime = perf.session_elapsed_seconds ?? perf.accumulated_audio_seconds ?? 0;

        // 各処理時間の表示
        document.getElementById("perf-transcription").textContent = `${transcriptionTime.toFixed(2)}秒`;
        document.getElementById("perf-normalization").textContent = `${normalizationTime.toFixed(2)}秒`;
        document.getElementById("perf-translation").textContent = `${translationTime.toFixed(2)}秒`;
        document.getElementById("perf-total").textContent = `${totalTime.toFixed(2)}秒`;
        document.getElementById("perf-recording").textContent = `${recordingTime.toFixed(1)}秒`;

        // バーグラフの幅を相対的に計算（最大値を100%とする）
        const maxTime = Math.max(transcriptionTime, normalizationTime, translationTime);
        if (maxTime > 0) {
            const transcriptionWidth = (transcriptionTime / maxTime) * 100;
            const normalizationWidth = (normalizationTime / maxTime) * 100;
            const translationWidth = (translationTime / maxTime) * 100;

            document.getElementById("perf-bar-transcription").style.width = `${transcriptionWidth}%`;
            document.getElementById("perf-bar-normalization").style.width = `${normalizationWidth}%`;
            document.getElementById("perf-bar-translation").style.width = `${translationWidth}%`;
        }

        // 処理オプションに応じて表示/非表示を更新
        this._updatePerformanceVisibility();
    }

    /**
     * パフォーマンス情報の表示/非表示を更新
     */
    _updatePerformanceVisibility() {
        const enableHiragana = document.getElementById("enable-hiragana").checked;
        const enableTranslation = document.getElementById("enable-translation").checked;

        const normalizationItem = document.getElementById("perf-item-normalization");
        const translationItem = document.getElementById("perf-item-translation");

        if (normalizationItem) {
            if (enableHiragana) {
                normalizationItem.classList.remove("hidden");
            } else {
                normalizationItem.classList.add("hidden");
            }
        }

        if (translationItem) {
            if (enableTranslation) {
                translationItem.classList.remove("hidden");
            } else {
                translationItem.classList.add("hidden");
            }
        }
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
        // パフォーマンス情報の表示も更新
        this._updatePerformanceVisibility();
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
        // パフォーマンス情報の表示も更新
        this._updatePerformanceVisibility();
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

        // セッションデータをリセット
        this.sessionStartTime = null;
        this.transcriptionHistory = [];

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

        // 履歴データから本文を生成
        for (const entry of this.transcriptionHistory) {
            const timestamp = this._formatTimestamp(entry.timestamp);
            content += `${timestamp} ${entry.text}\n`;

            // ひらがな正規化がある場合は追加
            if (processingOptions.enableHiragana && entry.hiragana) {
                content += `${entry.hiragana}\n`;
            }

            // 翻訳がある場合は追加
            if (processingOptions.enableTranslation && entry.translation) {
                content += `${entry.translation}\n`;
            }

            content += "\n";
        }

        return content;
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
            this.confirmedText.textContent = this.currentConfirmedText;

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
