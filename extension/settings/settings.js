/**
 * 設定画面のスクリプト
 */

// デフォルト設定
const DEFAULT_CONFIG = {
    apiServerUrl: 'ws://localhost:5001',
    showAdvancedFeatures: false,
    defaultHiragana: false,
    defaultTranslation: false
};

// DOM要素
const apiServerUrlInput = document.getElementById('apiServerUrl');
const showAdvancedFeaturesCheckbox = document.getElementById('showAdvancedFeatures');
const defaultHiraganaCheckbox = document.getElementById('defaultHiragana');
const defaultTranslationCheckbox = document.getElementById('defaultTranslation');
const advancedSubOptions = document.getElementById('advancedSubOptions');
const labelDefaultHiragana = document.getElementById('labelDefaultHiragana');
const labelDefaultTranslation = document.getElementById('labelDefaultTranslation');
const saveButton = document.getElementById('saveButton');
const resetButton = document.getElementById('resetButton');
const messageElement = document.getElementById('message');

/**
 * 上級者向けサブオプションの活性/非活性を切り替え
 *
 * @param {boolean} enabled
 */
function updateAdvancedSubOptionsState(enabled) {
    if (enabled) {
        labelDefaultHiragana.classList.remove('disabled');
        labelDefaultTranslation.classList.remove('disabled');
        defaultHiraganaCheckbox.disabled = false;
        defaultTranslationCheckbox.disabled = false;
    } else {
        labelDefaultHiragana.classList.add('disabled');
        labelDefaultTranslation.classList.add('disabled');
        defaultHiraganaCheckbox.disabled = true;
        defaultTranslationCheckbox.disabled = true;
    }
}

/**
 * メッセージを表示
 *
 * @param {string} text - メッセージテキスト
 * @param {string} type - メッセージタイプ（success, error）
 */
function showMessage(text, type = 'success') {
    messageElement.textContent = text;
    messageElement.className = `message ${type} show`;

    // 3秒後に非表示
    setTimeout(() => {
        messageElement.classList.remove('show');
    }, 3000);
}

/**
 * 設定を読み込んでフォームに反映
 */
async function loadSettings() {
    try {
        const config = await chrome.storage.sync.get(DEFAULT_CONFIG);

        apiServerUrlInput.value = config.apiServerUrl;
        showAdvancedFeaturesCheckbox.checked = config.showAdvancedFeatures;
        defaultHiraganaCheckbox.checked = config.defaultHiragana;
        defaultTranslationCheckbox.checked = config.defaultTranslation;

        // 上級者向けサブオプションの初期状態を反映
        updateAdvancedSubOptionsState(config.showAdvancedFeatures);

        console.log('設定を読み込みました:', config);
    } catch (error) {
        console.error('設定の読み込みエラー:', error);
        showMessage('設定の読み込みに失敗しました', 'error');
    }
}

/**
 * 設定を保存
 */
async function saveSettings() {
    try {
        const config = {
            apiServerUrl: apiServerUrlInput.value.trim(),
            showAdvancedFeatures: showAdvancedFeaturesCheckbox.checked,
            defaultHiragana: defaultHiraganaCheckbox.checked,
            defaultTranslation: defaultTranslationCheckbox.checked
        };

        // URLのバリデーション
        if (!config.apiServerUrl) {
            showMessage('APIサーバーURLを入力してください', 'error');
            return;
        }

        if (!config.apiServerUrl.startsWith('ws://') && !config.apiServerUrl.startsWith('wss://')) {
            showMessage('WebSocket URL（ws://またはwss://）を入力してください', 'error');
            return;
        }

        // 保存
        await chrome.storage.sync.set(config);

        console.log('設定を保存しました:', config);
        showMessage('設定を保存しました', 'success');
    } catch (error) {
        console.error('設定の保存エラー:', error);
        showMessage('設定の保存に失敗しました', 'error');
    }
}

/**
 * デフォルト設定に戻す
 */
async function resetSettings() {
    try {
        await chrome.storage.sync.set(DEFAULT_CONFIG);

        // フォームにも反映
        apiServerUrlInput.value = DEFAULT_CONFIG.apiServerUrl;
        showAdvancedFeaturesCheckbox.checked = DEFAULT_CONFIG.showAdvancedFeatures;
        defaultHiraganaCheckbox.checked = DEFAULT_CONFIG.defaultHiragana;
        defaultTranslationCheckbox.checked = DEFAULT_CONFIG.defaultTranslation;

        updateAdvancedSubOptionsState(DEFAULT_CONFIG.showAdvancedFeatures);

        console.log('設定をデフォルトに戻しました');
        showMessage('設定をデフォルトに戻しました', 'success');
    } catch (error) {
        console.error('設定のリセットエラー:', error);
        showMessage('設定のリセットに失敗しました', 'error');
    }
}

// イベントリスナー
saveButton.addEventListener('click', saveSettings);
resetButton.addEventListener('click', resetSettings);

// 上級者向け機能チェックボックスの変化に応じてサブオプションを切り替え
showAdvancedFeaturesCheckbox.addEventListener('change', (e) => {
    updateAdvancedSubOptionsState(e.target.checked);
});

// Enterキーで保存
apiServerUrlInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        saveSettings();
    }
});

// ページ読み込み時に設定を読み込む
document.addEventListener('DOMContentLoaded', loadSettings);
