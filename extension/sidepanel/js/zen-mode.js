// Zenモード管理（chrome.storage.local で状態を永続化）
(function () {
    const zenToggle = document.getElementById('zen-toggle');
    if (!zenToggle) return;

    // 保存済み状態を復元
    chrome.storage.local.get({ zenMode: false }, (result) => {
        if (result.zenMode) document.body.classList.add('zen-mode');
    });

    // トグル
    zenToggle.addEventListener('click', () => {
        document.body.classList.toggle('zen-mode');
        const isZen = document.body.classList.contains('zen-mode');
        chrome.storage.local.set({ zenMode: isZen });
    });
})();
