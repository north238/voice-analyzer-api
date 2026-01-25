/**
 * UIController - UI要素の更新管理
 *
 * DOM要素の参照を保持し、表示内容を更新します。
 */
class UIController {
    constructor() {
        // DOM要素の参照
        this.startButton = document.getElementById('start-button');
        this.stopButton = document.getElementById('stop-button');
        this.statusText = document.getElementById('status-text');
        this.volumeMeter = document.getElementById('volume-meter');
        this.volumeBar = document.getElementById('volume-bar');

        this.confirmedText = document.getElementById('confirmed-text');
        this.tentativeText = document.getElementById('tentative-text');
        this.hiraganaText = document.getElementById('hiragana-text');

        this.performanceInfo = document.getElementById('performance-info');
        this.deviceSelector = document.getElementById('device-selector');
    }

    /**
     * ステータスメッセージを設定
     *
     * @param {string} message - 表示メッセージ
     * @param {string} type - ステータスタイプ (info, success, error, recording)
     */
    setStatus(message, type = 'info') {
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
        this.volumeBar.style.width = `${normalized}%`;

        // 音量レベルに応じて色変更
        if (normalized > 50) {
            this.volumeBar.style.backgroundColor = '#4CAF50'; // 緑
        } else if (normalized > 20) {
            this.volumeBar.style.backgroundColor = '#FFC107'; // 黄
        } else {
            this.volumeBar.style.backgroundColor = '#9E9E9E'; // グレー
        }
    }

    /**
     * 文字起こし結果を更新
     *
     * @param {Object} data - 文字起こしデータ
     */
    updateTranscription(data) {
        console.log('🖥️ UI更新:', data);

        const transcription = data.transcription || {};
        const hiragana = data.hiragana || {};

        // 確定テキスト（太字・白色）
        this.confirmedText.textContent = transcription.confirmed || '';
        console.log('✅ 確定テキスト:', transcription.confirmed);

        // 暫定テキスト（イタリック・グレー）
        this.tentativeText.textContent = transcription.tentative || '';
        console.log('⏳ 暫定テキスト:', transcription.tentative);

        // ひらがな
        const hiraganaConfirmed = hiragana.confirmed || '';
        const hiraganaTentative = hiragana.tentative || '';
        this.hiraganaText.innerHTML = `<span class="confirmed">${this._escapeHtml(hiraganaConfirmed)}</span><span class="tentative">${this._escapeHtml(hiraganaTentative)}</span>`;
        console.log('🔤 ひらがな:', hiraganaConfirmed + hiraganaTentative);

        // パフォーマンス情報
        const perf = data.performance || {};
        this.performanceInfo.innerHTML = `
            <div>文字起こし: ${(perf.transcription_time || 0).toFixed(2)}秒</div>
            <div>累積音声: ${(perf.accumulated_audio_seconds || 0).toFixed(1)}秒</div>
            <div>合計: ${(perf.total_time || 0).toFixed(2)}秒</div>
        `;
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
            const audioInputs = devices.filter(device => device.kind === 'audioinput');

            this.deviceSelector.innerHTML = '';
            audioInputs.forEach((device, index) => {
                const option = document.createElement('option');
                option.value = device.deviceId;
                option.textContent = device.label || `マイク ${index + 1}`;
                this.deviceSelector.appendChild(option);
            });
        } catch (error) {
            console.error('デバイス一覧取得エラー:', error);
        }
    }

    /**
     * エラーメッセージを表示
     *
     * @param {string} message - エラーメッセージ
     */
    showError(message) {
        this.setStatus(`エラー: ${message}`, 'error');
        alert(`エラー: ${message}`);
    }

    /**
     * HTMLエスケープ
     *
     * @param {string} text - エスケープするテキスト
     * @returns {string} - エスケープ済みテキスト
     */
    _escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}
