/**
 * Service Worker
 *
 * Phase 6.2では最小限の実装。
 * 拡張機能アイコンのクリックでサイドパネルを開く。
 */

// 拡張機能アイコンをクリックしたときにサイドパネルを開く
chrome.action.onClicked.addListener((tab) => {
    chrome.sidePanel.open({ windowId: tab.windowId });
});

// インストール時の初期化
chrome.runtime.onInstalled.addListener(() => {
    console.log('リアルタイム音声文字起こし拡張機能がインストールされました');
});
