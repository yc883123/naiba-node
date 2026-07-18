/**
 * Naiba Tag Picker - 前端画廊扩展
 * 三标签页（画师/角色/IP）画廊，每页独立搜索 + 多选缩略图，
 * 选图结果以分组 JSON 写回隐藏控件 selection_data。
 */

import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// ========== 颜色常量（与项目暗色玻璃 + 紫色强调一致） ==========
const COLORS = {
    modalBg: "#1a1a2e",
    headerBg: "#16213e",
    contentBg: "#0f1729",
    accent: "#6c5ce7",
    accentHover: "#7c6cf7",
    danger: "#ff6b6b",
    success: "#2ed573",
    warning: "#ffa502",
    text: "#e0e0e0",
    textDim: "#888",
    border: "#2a3a5c",
    inputBg: "#0a0f1e",
    cardBg: "#16213e",
    cardBorder: "#2a3a5c",
};

const TABS = ["artist", "character", "ip", "gacha"];
const TAB_LABEL = { artist: "画师", character: "角色", ip: "IP", gacha: "扭蛋" };
const MAX_TOTAL_SELECTED = 64;

let currentModal = null;

// ========== 创建模态框 ==========
function createTagPickerModal(node) {
    if (currentModal) {
        currentModal.focus();
        return;
    }

    const overlay = document.createElement("div");
    overlay.style.cssText = `
        position:fixed;top:0;left:0;width:100%;height:100%;
        background:rgba(0,0,0,0.8);z-index:10000;
        display:flex;align-items:center;justify-content:center;
    `;

    const modal = document.createElement("div");
    modal.style.cssText = `
        width:92vw;max-width:1200px;height:88vh;
        background:${COLORS.modalBg};
        border-radius:8px;border:1px solid ${COLORS.border};
        display:flex;flex-direction:column;overflow:hidden;
        box-shadow:0 10px 40px rgba(0,0,0,0.5);
    `;

    // ---------- 标题栏 ----------
    const header = document.createElement("div");
    header.style.cssText = `
        display:flex;align-items:center;justify-content:space-between;
        padding:12px 16px;background:${COLORS.headerBg};
        border-bottom:1px solid ${COLORS.border};
    `;
    const title = document.createElement("div");
    title.textContent = "标签画廊 - Danbooru";
    title.style.cssText = `color:${COLORS.text};font-size:16px;font-weight:600;`;
    const closeBtn = document.createElement("div");
    closeBtn.textContent = "✕";
    closeBtn.style.cssText = `color:${COLORS.textDim};cursor:pointer;font-size:16px;padding:4px 8px;border-radius:4px;transition:all 0.15s;`;
    closeBtn.addEventListener("mouseenter", () => { closeBtn.style.color = COLORS.text; closeBtn.style.background = "rgba(255,255,255,0.1)"; });
    closeBtn.addEventListener("mouseleave", () => { closeBtn.style.color = COLORS.textDim; closeBtn.style.background = "none"; });
    closeBtn.addEventListener("click", () => closeModal());
    header.appendChild(title);
    header.appendChild(closeBtn);
    modal.appendChild(header);

    // ---------- 标签页 + 工具栏 ----------
    const toolbar = document.createElement("div");
    toolbar.style.cssText = `display:flex;flex-direction:column;gap:8px;padding:10px 16px;background:${COLORS.headerBg};border-bottom:1px solid ${COLORS.border};`;

    // 标签页行
    let currentTab = "artist";
    const tabGroup = document.createElement("div");
    tabGroup.style.cssText = `display:flex;gap:2px;background:${COLORS.inputBg};border-radius:4px;padding:2px;align-self:flex-start;`;
    const tabEls = {};
    TABS.forEach((cat) => {
        const t = document.createElement("div");
        t.textContent = TAB_LABEL[cat];
        t.style.cssText = `padding:6px 16px;border-radius:3px;cursor:pointer;font-size:13px;background:transparent;color:${COLORS.textDim};`;
        t.addEventListener("click", () => switchTab(cat));
        tabEls[cat] = t;
        tabGroup.appendChild(t);
    });
    toolbar.appendChild(tabGroup);

    // 搜索行
    const searchRow = document.createElement("div");
    searchRow.style.cssText = `display:flex;align-items:center;gap:8px;flex-wrap:wrap;`;

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.placeholder = "搜索关键词（如画师名 / 角色名 / 作品名）…";
    searchInput.style.cssText = `flex:1;min-width:180px;padding:8px 10px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:4px;color:${COLORS.text};font-size:13px;`;
    searchInput.addEventListener("keydown", (e) => { if (e.key === "Enter") doSearch(); });

    const countInput = document.createElement("input");
    countInput.type = "number";
    countInput.value = "50";
    countInput.min = "1";
    countInput.max = "100";
    countInput.title = "每页数量";
    countInput.style.cssText = `width:64px;padding:8px 6px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:4px;color:${COLORS.text};font-size:13px;`;

    // 单画师开关（仅画师页生效）
    const singleWrap = document.createElement("label");
    singleWrap.style.cssText = `display:flex;align-items:center;gap:4px;color:${COLORS.textDim};font-size:12px;cursor:pointer;`;
    const singleChk = document.createElement("input");
    singleChk.type = "checkbox";
    singleChk.checked = true;
    singleChk.style.cssText = `cursor:pointer;`;
    const singleLabel = document.createElement("span");
    singleLabel.textContent = "仅单画师";
    singleWrap.appendChild(singleChk);
    singleWrap.appendChild(singleLabel);

    const searchBtn = document.createElement("button");
    searchBtn.textContent = "搜索";
    searchBtn.style.cssText = `padding:8px 16px;background:${COLORS.accent};color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;`;
    searchBtn.addEventListener("mouseenter", () => searchBtn.style.background = COLORS.accentHover);
    searchBtn.addEventListener("mouseleave", () => searchBtn.style.background = COLORS.accent);
    searchBtn.addEventListener("click", () => doSearch());

    searchRow.appendChild(searchInput);
    searchRow.appendChild(countInput);
    searchRow.appendChild(singleWrap);
    searchRow.appendChild(searchBtn);
    toolbar.appendChild(searchRow);

    // ---------- 扭蛋面板（仅「扭蛋」标签页显示） ----------
    // 设计：用户只指定「每类抽几个」，部分随机时由后端从 Danbooru 实时随机取样，
    //       不要求手填候选（否则失去随机意义）。完全随机则忽略数量，随机抽 0~(a+c+i) 个。
    const gachaState = { artistN: 3, charN: 3, ipN: 3, resultTags: [] };

    const gachaPanel = document.createElement("div");
    gachaPanel.style.cssText = `display:none;flex-direction:column;gap:8px;padding:10px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:6px;`;

    const gachaTip = document.createElement("div");
    gachaTip.style.cssText = `color:${COLORS.textDim};font-size:11px;line-height:1.5;`;
    gachaTip.innerHTML = `分别指定每类要随机抽几个（0~10）。<b style="color:${COLORS.text}">部分随机</b>：从 Danbooru 实时随机抽 画师 a 个 + 角色 c 个 + IP i 个。<b style="color:${COLORS.text}">完全随机</b>：忽略数量，随机抽 0~(a+c+i) 个标签。`;
    gachaPanel.appendChild(gachaTip);

    // 三个数量输入（每类抽几个）
    function makeCountInput(labelText, key) {
        const wrap = document.createElement("div");
        wrap.style.cssText = "display:flex;align-items:center;gap:6px;flex:1;min-width:120px;";
        const lab = document.createElement("span");
        lab.textContent = labelText;
        lab.style.cssText = `color:${COLORS.textDim};font-size:12px;white-space:nowrap;`;
        const inp = document.createElement("input");
        inp.type = "number";
        inp.min = "0";
        inp.max = "10";
        inp.value = "3";
        inp.style.cssText = `width:56px;padding:6px;background:${COLORS.inputBg};border:1px solid ${COLORS.border};border-radius:4px;color:${COLORS.text};font-size:12px;`;
        inp.addEventListener("input", () => {
            const v = Math.max(0, Math.min(parseInt(inp.value) || 0, 10));
            gachaState[key] = v;
        });
        wrap.appendChild(lab);
        wrap.appendChild(inp);
        return { wrap, inp };
    }
    const gA = makeCountInput("画师数量", "artistN");
    const gC = makeCountInput("角色数量", "charN");
    const gI = makeCountInput("IP数量", "ipN");
    const gachaRow = document.createElement("div");
    gachaRow.style.cssText = "display:flex;gap:10px;flex-wrap:wrap;";
    gachaRow.appendChild(gA.wrap);
    gachaRow.appendChild(gC.wrap);
    gachaRow.appendChild(gI.wrap);
    gachaPanel.appendChild(gachaRow);

    // 按钮行
    const gachaBtns = document.createElement("div");
    gachaBtns.style.cssText = "display:flex;gap:10px;";
    const partialBtn = document.createElement("button");
    partialBtn.textContent = "部分随机";
    partialBtn.style.cssText = `padding:8px 16px;background:${COLORS.accent};color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:500;`;
    partialBtn.addEventListener("mouseenter", () => partialBtn.style.background = COLORS.accentHover);
    partialBtn.addEventListener("mouseleave", () => partialBtn.style.background = COLORS.accent);
    partialBtn.addEventListener("click", async () => {
        const a = gachaState.artistN, c = gachaState.charN, i = gachaState.ipN;
        statusLine.textContent = `部分随机生成中（画师 ${a} / 角色 ${c} / IP ${i}）…`;
        statusLine.style.color = COLORS.textDim;
        try {
            const resp = await api.fetchApi(`/naiba/tag/gacha_partial?artist=${a}&character=${c}&ip=${i}`);
            const data = await resp.json();
            // 后端返回 [{"tag","category"}]，兼容旧版纯字符串
            gachaState.resultTags = (data.tags || []).map((t) => typeof t === "string" ? { tag: t, category: "" } : t).filter((x) => x && x.tag);
        } catch (e) {
            console.warn("[NaibaTagPicker] 部分随机失败:", e);
            gachaState.resultTags = [];
        }
        renderGachaGallery();
    });
    const fullBtn = document.createElement("button");
    fullBtn.textContent = "完全随机";
    fullBtn.style.cssText = `padding:8px 16px;background:${COLORS.warning};color:#1a1a2e;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:600;`;
    fullBtn.addEventListener("click", async () => {
        const sum = gachaState.artistN + gachaState.charN + gachaState.ipN;
        const total = Math.floor(Math.random() * (sum + 1)); // 0~(a+c+i)
        statusLine.textContent = "完全随机生成中…";
        statusLine.style.color = COLORS.textDim;
        try {
            const resp = await api.fetchApi(`/naiba/tag/gacha_random?total=${total}`);
            const data = await resp.json();
            // 后端返回 [{"tag","category"}]，兼容旧版纯字符串
            gachaState.resultTags = (data.tags || []).map((t) => typeof t === "string" ? { tag: t, category: "" } : t).filter((x) => x && x.tag);
        } catch (e) {
            console.warn("[NaibaTagPicker] 完全随机失败:", e);
            gachaState.resultTags = [];
        }
        renderGachaGallery();
    });
    const clearGachaBtn = document.createElement("button");
    clearGachaBtn.textContent = "清除";
    clearGachaBtn.style.cssText = `padding:8px 16px;background:${COLORS.danger};color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:500;`;
    clearGachaBtn.addEventListener("mouseenter", () => clearGachaBtn.style.background = "#ff8585");
    clearGachaBtn.addEventListener("mouseleave", () => clearGachaBtn.style.background = COLORS.danger);
    clearGachaBtn.addEventListener("click", () => {
        gachaState.resultTags = [];
        renderGachaGallery();
    });
    gachaBtns.appendChild(partialBtn);
    gachaBtns.appendChild(fullBtn);
    gachaBtns.appendChild(clearGachaBtn);
    gachaPanel.appendChild(gachaBtns);
    toolbar.appendChild(gachaPanel);

    modal.appendChild(toolbar);

    // ---------- 主体（缩略图墙） ----------
    const mainContent = document.createElement("div");
    mainContent.style.cssText = `flex:1;overflow-y:auto;padding:12px 16px;background:${COLORS.contentBg};`;

    const statusLine = document.createElement("div");
    statusLine.style.cssText = `color:${COLORS.textDim};font-size:12px;margin-bottom:8px;min-height:16px;`;
    mainContent.appendChild(statusLine);

    const grid = document.createElement("div");
    grid.style.cssText = `display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:10px;`;
    mainContent.appendChild(grid);
    modal.appendChild(mainContent);

    // ---------- 底部状态栏 ----------
    const footer = document.createElement("div");
    footer.style.cssText = `display:flex;align-items:center;justify-content:space-between;gap:12px;padding:10px 16px;background:${COLORS.headerBg};border-top:1px solid ${COLORS.border};`;

    const countDisplay = document.createElement("div");
    countDisplay.style.cssText = `color:${COLORS.text};font-size:13px;`;

    const applyBtn = document.createElement("button");
    applyBtn.style.cssText = `padding:8px 18px;background:${COLORS.success};color:white;border:none;border-radius:4px;cursor:pointer;font-size:13px;font-weight:500;`;
    applyBtn.addEventListener("click", () => applySelection());
    footer.appendChild(countDisplay);
    footer.appendChild(applyBtn);
    modal.appendChild(footer);

    overlay.appendChild(modal);
    document.body.appendChild(overlay);
    currentModal = modal;
    modal.focus = () => { overlay.style.display = "flex"; };

    // ========== 状态 ==========
    const selectedMap = { artist: new Map(), character: new Map(), ip: new Map() };
    const tabState = {
        artist: { items: [], query: "", limit: 50, single: true, loaded: false },
        character: { items: [], query: "", limit: 50, single: true, loaded: false },
        ip: { items: [], query: "", limit: 50, single: true, loaded: false },
        gacha: { items: [], query: "", limit: 50, single: true, loaded: false },
    };
    let loading = false;
    // 预览图：仿 comfyui-anima-t8 的客户端缓存 + 并发队列（两步法 JSON 代理 URL）
    const previewCache = new Map();   // name -> image_url（"" = 拉过但无图）
    const previewQueue = [];
    let previewActive = 0;
    const MAX_PREVIEW_CONCURRENCY = 4;
    let previewGen = 0;               // 每次切换 tab/重渲染自增，丢弃过期请求结果
    const PLACEHOLDER_SVG = "data:image/svg+xml;base64," + btoa(
        '<svg xmlns="http://www.w3.org/2000/svg" width="140" height="120">' +
        '<rect width="100%" height="100%" fill="#16213e"/>' +
        '<text x="50%" y="50%" fill="#555" font-size="11" text-anchor="middle" dominant-baseline="middle">na</text>' +
        '</svg>');
    // 失败预览自动重试：Danbooru 匿名 posts.json 偶发 403/限流，限流解除后图会自动补全
    let retryTimer = null;
    let retryRound = 0;
    const MAX_RETRY_ROUNDS = 3;

    function scheduleRetrySweep() {
        if (retryTimer || retryRound >= MAX_RETRY_ROUNDS) return;
        retryTimer = setTimeout(() => {
            retryTimer = null;
            retryRound++;
            const errs = grid.querySelectorAll("img.tp-err");
            errs.forEach((img) => {
                const name = img.dataset.name;
                if (name && img.isConnected) {
                    img.classList.remove("tp-err");
                    img.src = PLACEHOLDER_SVG;
                    schedulePreview(name, img);
                }
            });
            if (grid.querySelectorAll("img.tp-err").length && retryRound < MAX_RETRY_ROUNDS) {
                scheduleRetrySweep();
            }
        }, 15000);
    }

    function totalSelected() {
        return selectedMap.artist.size + selectedMap.character.size + selectedMap.ip.size;
    }

    function updateCountDisplay() {
        countDisplay.textContent = `画师 ${selectedMap.artist.size} · 角色 ${selectedMap.character.size} · IP ${selectedMap.ip.size}（共 ${totalSelected()}/${MAX_TOTAL_SELECTED}）`;
        applyBtn.textContent = `应用选中 (${totalSelected()})`;
    }

    function updateTabStyle() {
        TABS.forEach((cat) => {
            const active = cat === currentTab;
            tabEls[cat].style.background = active ? COLORS.accent : "transparent";
            tabEls[cat].style.color = active ? "white" : COLORS.textDim;
        });
        // 单画师开关仅画师页可用
        const isArtist = currentTab === "artist";
        singleWrap.style.display = isArtist ? "flex" : "none";
        // 扭蛋页：显示扭蛋面板、隐藏普通搜索行；其余页相反
        const isGacha = currentTab === "gacha";
        gachaPanel.style.display = isGacha ? "flex" : "none";
        searchRow.style.display = isGacha ? "none" : "flex";
    }

    function switchTab(cat) {
        currentTab = cat;
        if (cat === "gacha") {
            updateTabStyle();
            renderGachaGallery();
            return;
        }
        searchInput.value = tabState[cat].query;
        countInput.value = String(tabState[cat].limit);
        singleChk.checked = tabState[cat].single;
        updateTabStyle();
        if (!tabState[cat].loaded) {
            doSearch();
        } else {
            renderGallery();
        }
    }

    async function doSearch() {
        if (loading) return;
        const st = tabState[currentTab];
        st.query = searchInput.value.trim();
        st.limit = Math.max(1, Math.min(parseInt(countInput.value) || 50, 100));
        st.single = singleChk.checked;
        loading = true;
        statusLine.textContent = "搜索中…";
        grid.innerHTML = "";
        try {
            const params = new URLSearchParams({
                q: st.query,
                category: currentTab,
                limit: st.limit,
                single: st.single ? "true" : "false",
            });
            const resp = await api.fetchApi(`/naiba/tag/search?${params.toString()}`);
            const data = await resp.json();
            st.items = data.items || [];
            st.warn = data.warn || null;
            st.loaded = true;
            renderGallery();
        } catch (e) {
            console.warn("[NaibaTagPicker] 搜索失败:", e);
            st.items = [];
            st.warn = "搜索请求失败，请检查网络或 ComfyUI 后端日志";
            renderGallery();
        } finally {
            loading = false;
        }
    }

    function schedulePreview(name, img) {
        const job = () => {
            previewActive++;
            const gen = previewGen;
            // 客户端超时 15s，避免某请求挂住占用并发名额
            const timeout = new Promise((_, rej) =>
                setTimeout(() => rej(new Error("timeout 15s")), 15000));
            const run = api.fetchApi(`/naiba/tag/preview?name=${encodeURIComponent(name)}`)
                .then((r) => r.json())
                .then((d) => {
                    const url = (d && d.image_url) || "";
                    previewCache.set(name, url);
                    if (gen !== previewGen) return;          // 已切换 tab，丢弃
                    if (url && img.isConnected) {
                        img.onerror = () => {
                            img.onerror = null;
                            img.src = PLACEHOLDER_SVG;
                            img.classList.add("tp-err");
                            scheduleRetrySweep();
                        };
                        img.classList.remove("tp-err");
                        img.src = url;
                    } else if (img.isConnected) {
                        img.src = PLACEHOLDER_SVG;
                        img.classList.add("tp-err");
                        scheduleRetrySweep();
                    }
                });
            return Promise.race([run, timeout]).catch((e) => {
                if (gen === previewGen && img.isConnected) {
                    img.src = PLACEHOLDER_SVG;
                    img.classList.add("tp-err");
                    scheduleRetrySweep();
                }
            }).finally(() => {
                previewActive--;
                while (previewActive < MAX_PREVIEW_CONCURRENCY && previewQueue.length) {
                    previewQueue.shift()();
                }
            });
        };
        if (previewActive < MAX_PREVIEW_CONCURRENCY) job();
        else previewQueue.push(job);
    }

    function renderGallery() {
        const st = tabState[currentTab];
        grid.innerHTML = "";
        previewQueue.length = 0;
        previewGen++;                                 // 丢弃上一轮未完成的预览请求结果
        if (st.warn) {
            statusLine.textContent = st.warn;
            statusLine.style.color = COLORS.warning;
        } else {
            statusLine.textContent = `共 ${st.items.length} 条结果`;
            statusLine.style.color = COLORS.textDim;
        }
        if (!st.items.length) return;

        st.items.forEach((item) => {
            const tag = item.tag || "";
            const isSel = selectedMap[currentTab].has(item.id);

            const card = document.createElement("div");
            card.style.cssText = `
                position:relative;background:${COLORS.cardBg};border:2px solid ${isSel ? COLORS.accent : COLORS.cardBorder};
                border-radius:6px;overflow:hidden;cursor:pointer;transition:transform 0.12s, box-shadow 0.12s;
                ${isSel ? `box-shadow:0 0 0 2px ${COLORS.accent}, 0 0 12px ${COLORS.accent}88;` : ""}
            `;
            card.addEventListener("mouseenter", () => { if (!isSel) card.style.transform = "translateY(-2px)"; });
            card.addEventListener("mouseleave", () => { card.style.transform = "none"; });

            const img = document.createElement("img");
            img.loading = "lazy";
            img.style.cssText = "width:100%;height:120px;object-fit:cover;display:block;background:#0a0f1e;";
            img.src = PLACEHOLDER_SVG;                // 先占位，待懒加载替换
            card.appendChild(img);

            const cap = document.createElement("div");
            cap.style.cssText = `padding:4px 6px;font-size:11px;color:${COLORS.text};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;`;
            cap.textContent = tag || String(item.id);
            card.appendChild(cap);

            // 选中角标
            const badge = document.createElement("div");
            badge.textContent = "✓";
            badge.style.cssText = `position:absolute;top:4px;right:4px;width:18px;height:18px;border-radius:50%;
                background:${COLORS.accent};color:white;font-size:12px;display:flex;align-items:center;justify-content:center;
                ${isSel ? "display:flex;" : "display:none;"}`;
            card.appendChild(badge);

            card.addEventListener("click", () => {
                const map = selectedMap[currentTab];
                if (map.has(item.id)) {
                    map.delete(item.id);
                } else {
                    if (totalSelected() >= MAX_TOTAL_SELECTED) {
                        alert(`最多可选 ${MAX_TOTAL_SELECTED} 张（含三类合计）`);
                        return;
                    }
                    map.set(item.id, { id: item.id, preview_url: item.preview_url, tag });
                }
                renderGallery();
                updateCountDisplay();
            });

            grid.appendChild(card);

            // 预览图：命中客户端缓存直接用，否则入队并发拉取（仿 anima-t8）
            const cached = previewCache.get(tag);
            if (cached) {
                if (cached) img.src = cached;
                else img.classList.add("tp-err");
            } else {
                schedulePreview(tag, img);
            }
        });
    }

    function renderGachaGallery() {
        const tags = gachaState.resultTags || [];
        grid.innerHTML = "";
        previewQueue.length = 0;
        previewGen++;                                 // 丢弃上一轮未完成的预览请求结果
        if (!tags.length) {
            statusLine.textContent = "尚未生成扭蛋结果。输入候选后点「部分随机」，或直接点「完全随机」。";
            statusLine.style.color = COLORS.textDim;
            return;
        }
        statusLine.textContent = `扭蛋结果：共 ${tags.length} 个随机标签（上限 ${gachaState.artistN + gachaState.charN + gachaState.ipN}）`;
        statusLine.style.color = COLORS.success;

        tags.forEach((item, idx) => {
            const tag = item.tag || "";
            const card = document.createElement("div");
            card.style.cssText = `
                position:relative;background:${COLORS.cardBg};border:1px solid ${COLORS.cardBorder};
                border-radius:6px;overflow:hidden;
            `;
            const img = document.createElement("img");
            img.loading = "lazy";
            img.dataset.name = tag;
            img.style.cssText = "width:100%;height:120px;object-fit:cover;display:block;background:#0a0f1e;";
            img.src = PLACEHOLDER_SVG;                // 先占位，待懒加载替换
            card.appendChild(img);

            const cap = document.createElement("div");
            cap.style.cssText = `padding:4px 6px;font-size:11px;color:${COLORS.text};white-space:nowrap;overflow:hidden;text-overflow:ellipsis;`;
            cap.textContent = tag;
            card.appendChild(cap);

            // 单标签删除按钮：移除此扭蛋结果（不想要的标签）
            const del = document.createElement("div");
            del.textContent = "✕";
            del.title = "删除此标签";
            del.style.cssText = `position:absolute;top:4px;right:4px;width:18px;height:18px;border-radius:50%;
                background:${COLORS.danger};color:white;font-size:12px;display:flex;align-items:center;justify-content:center;
                cursor:pointer;z-index:2;transition:background 0.15s;`;
            del.addEventListener("mouseenter", () => del.style.background = "#ff8585");
            del.addEventListener("mouseleave", () => del.style.background = COLORS.danger);
            del.addEventListener("click", () => {
                gachaState.resultTags = gachaState.resultTags.filter((_, i) => i !== idx);
                renderGachaGallery();
            });
            card.appendChild(del);

            grid.appendChild(card);

            // 预览图：命中客户端缓存直接用，否则入队并发拉取（仿 anima-t8）
            const cached = previewCache.get(tag);
            if (cached) {
                if (cached) img.src = cached;
                else img.classList.add("tp-err");
            } else {
                schedulePreview(tag, img);
            }
        });
    }

    function clearAll() {
        selectedMap.artist.clear();
        selectedMap.character.clear();
        selectedMap.ip.clear();
        gachaState.resultTags = [];
        const sd = node.widgets?.find((w) => w.name === "selection_data");
        if (sd) sd.value = "{}";
        const gd = node.widgets?.find((w) => w.name === "gacha_data");
        if (gd) gd.value = JSON.stringify({ tags: [] });
        updateCountDisplay();
        renderGallery();
        renderGachaGallery();
        if (node._updateTagPickerPreview) node._updateTagPickerPreview();
    }
    node._tpClearSelection = clearAll;   // 供节点外部「清除已选」按钮调用，同步清空弹窗内内存状态

    function applySelection() {
        const gachaTags = gachaState.resultTags || [];
        if (totalSelected() === 0 && gachaTags.length === 0) {
            alert("请先选择至少一张图，或在扭蛋页生成随机结果");
            return;
        }
        const result = { artist: [], character: [], ip: [], gacha: { tags: gachaTags } };
        TABS.filter((c) => c !== "gacha").forEach((cat) => {
            selectedMap[cat].forEach((it) => {
                result[cat].push({ id: it.id, preview_url: it.preview_url, tag: it.tag });
            });
        });
        const widget = node.widgets?.find((w) => w.name === "selection_data");
        if (widget) widget.value = JSON.stringify(result);
        const gachaWidget = node.widgets?.find((w) => w.name === "gacha_data");
        if (gachaWidget) gachaWidget.value = JSON.stringify({ tags: gachaTags });
        if (node._updateTagPickerPreview) node._updateTagPickerPreview();
        closeModal();
    }

    function closeModal() {
        previewQueue.length = 0;
        previewGen++;                                 // 让进行中的预览请求结果作废
        document.body.removeChild(overlay);
        currentModal = null;
        document.removeEventListener("keydown", escHandler);
    }
    const escHandler = (e) => { if (e.key === "Escape") closeModal(); };
    document.addEventListener("keydown", escHandler);

    // ========== 初始化：从已存控件恢复选中 ==========
    const existingWidget = node.widgets?.find((w) => w.name === "selection_data");
    if (existingWidget && existingWidget.value) {
        try {
            const saved = JSON.parse(existingWidget.value);
            TABS.filter((c) => c !== "gacha").forEach((cat) => {
                (saved[cat] || []).forEach((it) => {
                    if (it && it.id != null && it.preview_url) {
                        selectedMap[cat].set(it.id, { id: it.id, preview_url: it.preview_url, tag: it.tag || "" });
                    }
                });
            });
            if (Array.isArray(saved.gacha?.tags)) {
                gachaState.resultTags = saved.gacha.tags.filter(Boolean).map((t) =>
                    typeof t === "string" ? { tag: t, category: "" } : (t && t.tag ? t : null)
                ).filter(Boolean);
            }
        } catch (e) { /* ignore */ }
    }
    // 从 gacha_data 控件恢复扭蛋结果（与 selection_data 中的 gacha 互为备份）
    const gachaWidget = node.widgets?.find((w) => w.name === "gacha_data");
    if (gachaWidget && gachaWidget.value) {
        try {
            const gd = JSON.parse(gachaWidget.value);
            if (Array.isArray(gd.tags) && gd.tags.length && !gachaState.resultTags.length) {
                gachaState.resultTags = gd.tags.filter(Boolean).map((t) =>
                    typeof t === "string" ? { tag: t, category: "" } : (t && t.tag ? t : null)
                ).filter(Boolean);
            }
        } catch (e) { /* ignore */ }
    }
    updateTabStyle();
    updateCountDisplay();
    // 默认加载画师页
    switchTab("artist");
}

// ========== 注册扩展 ==========
app.registerExtension({
    name: "naiba.TagPicker",

    async beforeRegisterNodeDef(nodeType, nodeData, appInstance) {
        if (nodeData.name !== "NaibaTagPicker") return;

        const origOnNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            origOnNodeCreated?.apply(this, arguments);
            const node = this;

            // 隐藏 selection_data / gacha_data / gacha_mode 控件（由前端面板与按钮代理）
            const hiddenWidgets = ["selection_data", "gacha_data", "gacha_mode"];
            hiddenWidgets.forEach((name) => {
                const w = node.widgets?.find((x) => x.name === name);
                if (w) {
                    w.hidden = true;
                    if (w.inputEl) w.inputEl.style.display = "none";
                    if (w.element) w.element.style.display = "none";
                }
            });

            // 扭蛋模式开关按钮（位于预览区上方）
            const gachaBtn = document.createElement("button");
            gachaBtn.style.cssText = `
                width:100%;padding:8px;margin:8px 0 0;
                background:${COLORS.inputBg};color:${COLORS.text};
                border:1px solid ${COLORS.border};border-radius:6px;cursor:pointer;
                font-size:12px;font-weight:500;transition:all 0.2s;
            `;
            const refreshGachaBtn = () => {
                const w = node.widgets?.find((x) => x.name === "gacha_mode");
                const on = !!(w && w.value);
                gachaBtn.textContent = on ? "扭蛋模式：开（输出 RANDOM_TAGS）" : "扭蛋模式：关";
                gachaBtn.style.background = on ? COLORS.success : COLORS.inputBg;
                gachaBtn.style.color = on ? "white" : COLORS.text;
                gachaBtn.style.border = `1px solid ${on ? COLORS.success : COLORS.border}`;
            };
            gachaBtn.addEventListener("click", () => {
                const w = node.widgets?.find((x) => x.name === "gacha_mode");
                if (w) {
                    w.value = !w.value;
                    refreshGachaBtn();
                    updatePreview();
                }
            });

            // 已选摘要预览区
            const previewArea = document.createElement("div");
            previewArea.style.cssText = `
                width:100%;min-height:54px;max-height:130px;background:${COLORS.inputBg};
                border:1px solid ${COLORS.border};border-radius:4px;
                margin:8px 0;padding:6px;overflow-y:auto;
                font-size:11px;color:${COLORS.text};
            `;

            const updatePreview = () => {
                const w = node.widgets?.find((x) => x.name === "selection_data");
                const gw = node.widgets?.find((x) => x.name === "gacha_data");
                const gachaOn = !!node.widgets?.find((x) => x.name === "gacha_mode")?.value;
                let html = "";
                try {
                    const data = JSON.parse(w?.value || "{}");
                    const fmt = (label, arr) => (arr && arr.length)
                        ? `<div style="margin:2px 0;"><span style="color:${COLORS.accent};">${label} ${arr.length}：</span>${arr.map((x) => x.tag).filter(Boolean).join(", ")}</div>`
                        : "";
                    html += fmt("画师", data.artist || []) + fmt("角色", data.character || []) + fmt("IP", data.ip || []);
                    const merged = [...(data.artist || []), ...(data.character || []), ...(data.ip || [])]
                        .map((x) => x.tag).filter(Boolean);
                    if (merged.length) {
                        html += `<div style="margin:2px 0;"><span style="color:${COLORS.text};">合并 ${merged.length}：</span>${merged.join(", ")}</div>`;
                    }
                } catch (e) { /* ignore */ }
                try {
                    const gd = JSON.parse(gw?.value || "{}");
                    const gt = Array.isArray(gd.tags) ? gd.tags.filter(Boolean) : [];
                    if (gt.length) {
                        const names = gt.map((x) => (x && x.tag) || x).join(", ");
                        html += `<div style="margin:2px 0;"><span style="color:${gachaOn ? COLORS.success : COLORS.textDim};">扭蛋标签 ${gt.length}${gachaOn ? "" : "（未启用）"}：</span>${names}</div>`;
                    }
                } catch (e) { /* ignore */ }
                if (!html) {
                    html = `<div style="color:${COLORS.textDim};text-align:center;padding:14px;">点击下方按钮选择标签</div>`;
                }
                previewArea.innerHTML = html;
            };
            updatePreview();
            refreshGachaBtn();
            node._updateTagPickerPreview = updatePreview;

            // 打开画廊按钮
            const openBtn = document.createElement("button");
            openBtn.textContent = "打开标签画廊";
            openBtn.style.cssText = `
                width:100%;padding:10px;margin:8px 0;
                background:${COLORS.accent};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:13px;font-weight:500;transition:background 0.2s;
            `;
            openBtn.addEventListener("mouseenter", () => openBtn.style.background = COLORS.accentHover);
            openBtn.addEventListener("mouseleave", () => openBtn.style.background = COLORS.accent);
            openBtn.addEventListener("click", () => createTagPickerModal(node));

            // 清除已选按钮：清空 selection_data / gacha_data 控件与弹窗内存状态
            const clearBtn = document.createElement("button");
            clearBtn.textContent = "清除已选";
            clearBtn.style.cssText = `
                width:100%;padding:8px;margin:4px 0;
                background:${COLORS.danger};color:white;
                border:none;border-radius:6px;cursor:pointer;
                font-size:12px;font-weight:500;transition:background 0.2s;
            `;
            clearBtn.addEventListener("mouseenter", () => clearBtn.style.background = "#ff8585");
            clearBtn.addEventListener("mouseleave", () => clearBtn.style.background = COLORS.danger);
            clearBtn.addEventListener("click", () => {
                const sd = node.widgets?.find((x) => x.name === "selection_data");
                if (sd) sd.value = "{}";
                const gd = node.widgets?.find((x) => x.name === "gacha_data");
                if (gd) gd.value = JSON.stringify({ tags: [] });
                if (node._tpClearSelection) node._tpClearSelection();  // 弹窗打开时同步清内存
                updatePreview();
            });

            const container = document.createElement("div");
            container.style.cssText = "display:flex;flex-direction:column;gap:4px;width:100%;box-sizing:border-box;";
            container.appendChild(gachaBtn);
            container.appendChild(previewArea);
            container.appendChild(clearBtn);
            container.appendChild(openBtn);

            const domWidget = node.addDOMWidget("tag_picker_container", "TAG_PICKER_CONTAINER", container, {
                getValue() { return ""; },
                setValue() {},
            });

            // 修复：ComfyUI 会给 DOM 面板注入 h-full，父容器初始高度 0 时面板塌缩，
            // 导致按钮溢出节点黑框。强制按内容真实高度展开，节点边框随内容自适应。
            const panelEl = domWidget.element || container;
            [panelEl, container].forEach((el) => {
                if (!el) return;
                el.classList.remove("h-full");
                el.style.height = "auto";
                el.style.minHeight = "max-content";
            });

            node.minWidth = 240;
            node.minHeight = 180;
        };
    },
});
