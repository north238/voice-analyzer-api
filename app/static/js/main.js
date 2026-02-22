// 入力ソース切り替え（pill型タブ）
document.querySelectorAll(".source-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        document.querySelectorAll(".source-btn").forEach((b) => {
            b.classList.remove(
                "bg-white",
                "dark:bg-slate-800",
                "shadow-sm",
                "text-slate-700",
                "dark:text-slate-200",
            );
            b.classList.add("text-slate-400");
        });
        btn.classList.add("bg-white", "shadow-sm", "text-slate-700");
        btn.classList.remove("text-slate-400");
        const radio = document.getElementById("radio-" + btn.dataset.source);
        if (radio) radio.click();
    });
});

// 録音開始/停止でのソースエリアフェードアウトは ui-controller.js の setButtonsState で制御

// Zenモード
function toggleZen() {
    document.body.classList.toggle("zen-mode");
    localStorage.setItem("zenMode", document.body.classList.contains("zen-mode"));
}
document.getElementById("zen-toggle").addEventListener("click", toggleZen);
document.getElementById("zen-exit-float").addEventListener("click", toggleZen);
if (localStorage.getItem("zenMode") === "true") {
    document.body.classList.add("zen-mode");
}

// ダークモード
document.getElementById("dark-toggle").addEventListener("click", () => {
    document.documentElement.classList.toggle("dark");
    localStorage.setItem("darkMode", document.documentElement.classList.contains("dark"));
});
if (localStorage.getItem("darkMode") === "true") {
    document.documentElement.classList.add("dark");
}

// モバイル設定ドロワー
const settingsBtn = document.getElementById("settings-btn");
const settingsDrawer = document.getElementById("settings-drawer");
const settingsOverlay = document.getElementById("settings-overlay");
const settingsClose = document.getElementById("settings-close");

function openDrawer() {
    settingsDrawer.classList.remove("translate-y-full");
    settingsOverlay.classList.remove("hidden");
}
function closeDrawer() {
    settingsDrawer.classList.add("translate-y-full");
    settingsOverlay.classList.add("hidden");
}

settingsBtn.addEventListener("click", openDrawer);
settingsClose.addEventListener("click", closeDrawer);
settingsOverlay.addEventListener("click", closeDrawer);

// モバイルトグル → デスクトップトグルに連動 + カードタブの表示制御
["hiragana", "translation"].forEach((key) => {
    const mobile = document.getElementById("enable-" + key + "-mobile");
    const desktop = document.getElementById("enable-" + key);
    const tab = document.getElementById("mobile-tab-" + key);
    if (mobile && desktop) {
        mobile.addEventListener("change", () => {
            desktop.checked = mobile.checked;
            desktop.dispatchEvent(new Event("change"));
            // タブの表示/非表示を切り替え
            if (tab) tab.classList.toggle("hidden", !mobile.checked);
            // OFFにしたとき、そのパネルが表示中なら文字起こしに戻す
            if (!mobile.checked) {
                const panel = document.getElementById("mobile-panel-" + key);
                if (panel && !panel.classList.contains("hidden")) {
                    switchMobilePanel("transcription");
                }
            }
        });
    }
});

// モバイルカードタブの切り替え
function switchMobilePanel(panelName) {
    ["transcription", "hiragana", "translation"].forEach((name) => {
        const panel = document.getElementById("mobile-panel-" + name);
        const btn = document.querySelector('[data-panel="' + name + '"]');
        if (panel) panel.classList.toggle("hidden", name !== panelName);
        if (btn) btn.classList.toggle("active", name === panelName);
    });
}

document.querySelectorAll(".mobile-tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
        switchMobilePanel(btn.dataset.panel);
    });
});
