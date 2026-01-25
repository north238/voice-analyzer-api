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

    this.performanceInfo = document.getElementById("performance-info");
    this.deviceSelector = document.getElementById("device-selector");
    this.toastContainer = document.getElementById("toast-container");

    // タイピングアニメーション用の状態管理
    this.previousConfirmedText = "";
    this.previousTentativeText = "";
    this.previousHiraganaConfirmed = "";
    this.previousHiraganaTentative = "";
    this.typingTimers = [];
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

    // 確定テキスト（タイピングアニメーション）
    if (newConfirmedText !== this.previousConfirmedText) {
      console.log("✅ 確定テキスト:", newConfirmedText);
      this._typeText(
        this.confirmedText,
        this.previousConfirmedText,
        newConfirmedText,
        50, // 50ms間隔
      );
      this.previousConfirmedText = newConfirmedText;
    }

    // 暫定テキスト（タイピングアニメーション）
    if (newTentativeText !== this.previousTentativeText) {
      console.log("⏳ 暫定テキスト:", newTentativeText);
      this._typeText(
        this.tentativeText,
        this.previousTentativeText,
        newTentativeText,
        30, // 30ms間隔
      );
      this.previousTentativeText = newTentativeText;
    }

    // ひらがな（タイピングアニメーション）
    const hiraganaChanged =
      newHiraganaConfirmed !== this.previousHiraganaConfirmed ||
      newHiraganaTentative !== this.previousHiraganaTentative;

    if (hiraganaChanged) {
      console.log("🔤 ひら���な:", newHiraganaConfirmed + newHiraganaTentative);
      const previousFullHiragana =
        this.previousHiraganaConfirmed + this.previousHiraganaTentative;

      // ひらがなは特殊処理（confirmed/tentativeのspan構造を保持）
      this._typeHiragana(
        previousFullHiragana,
        newHiraganaConfirmed,
        newHiraganaTentative,
        30, // 30ms間隔
      );

      this.previousHiraganaConfirmed = newHiraganaConfirmed;
      this.previousHiraganaTentative = newHiraganaTentative;
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
          const displayedConfirmed = currentDisplayedText.slice(
            0,
            newConfirmed.length,
          );
          const displayedTentative = currentDisplayedText.slice(
            newConfirmed.length,
          );

          this.hiraganaText.innerHTML =
            `<span class="confirmed">${this._escapeHtml(displayedConfirmed)}</span>` +
            `<span class="tentative">${this._escapeHtml(displayedTentative)}</span>`;

          const timer = setTimeout(typeNextChar, interval);
          this.typingTimers.push(timer);
        }
      };

      // 初期表示
      const displayedConfirmed = oldFullText.slice(
        0,
        Math.min(oldFullText.length, newConfirmed.length),
      );
      const displayedTentative = oldFullText.slice(
        Math.min(oldFullText.length, newConfirmed.length),
      );
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
      const audioInputs = devices.filter(
        (device) => device.kind === "audioinput",
      );

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
}
