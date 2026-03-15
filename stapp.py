import streamlit as st
import os, json, time, glob, threading, re
from datetime import datetime
from agentmain import GeneraticAgent

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_DIR = os.path.join(PROJECT_DIR, "history")
MEMORY_DIR = os.path.join(PROJECT_DIR, "memory")
os.makedirs(HISTORY_DIR, exist_ok=True)

# ─── Helper Functions ───

def get_saved_histories():
    files = glob.glob(os.path.join(HISTORY_DIR, "*.json"))
    histories = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                data = json.load(fp)
            histories.append({
                "path": f,
                "name": data.get("name", os.path.basename(f)),
                "timestamp": data.get("timestamp", ""),
                "preview": data.get("preview", ""),
                "msg_count": len(data.get("messages", []))
            })
        except:
            pass
    histories.sort(key=lambda x: x["timestamp"], reverse=True)
    return histories

def save_current_history(name=None):
    if not st.session_state.get("messages"):
        return None
    if name is None or name.strip() == "":
        for msg in st.session_state.messages:
            if msg["role"] == "user":
                name = msg["content"][:40].replace("/", "_").replace("\\", "_")
                break
        if not name:
            name = f"对话_{datetime.now().strftime('%m%d_%H%M')}"
    
    timestamp = datetime.now().isoformat()
    preview = ""
    for msg in st.session_state.messages[-3:]:
        preview += f"[{msg['role']}] {msg['content'][:50]}... "
    
    # Get agent internal history
    agent_history = []
    agent_key_info = ""
    agent = st.session_state.get("agent")
    if agent:
        agent_history = list(agent.history)
        if agent.handler and hasattr(agent.handler, 'key_info'):
            agent_key_info = agent.handler.key_info or ""
    
    data = {
        "name": name,
        "timestamp": timestamp,
        "preview": preview.strip(),
        "messages": st.session_state.messages,
        "agent_history": agent_history,
        "agent_key_info": agent_key_info
    }
    
    filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{name[:20]}.json"
    filename = "".join(c for c in filename if c.isalnum() or c in "._- ")
    filepath = os.path.join(HISTORY_DIR, filename)
    
    if st.session_state.get("current_history_path"):
        filepath = st.session_state.current_history_path
    
    with open(filepath, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    
    st.session_state.current_history_path = filepath
    st.session_state.current_history_name = name
    return filepath

def load_history(filepath):
    with open(filepath, 'r', encoding='utf-8') as fp:
        data = json.load(fp)
    
    st.session_state.messages = data.get("messages", [])
    agent_history = data.get("agent_history", [])
    agent_key_info = data.get("agent_key_info", "")
    
    # Recreate agent with restored state
    agent = _init_agent()
    agent.history = agent_history
    if agent.handler and agent_key_info:
        agent.handler.key_info = agent_key_info
    
    st.session_state.current_history_path = filepath
    st.session_state.current_history_name = data.get("name", "")

def delete_history(filepath):
    try:
        os.remove(filepath)
        if st.session_state.get("current_history_path") == filepath:
            st.session_state.current_history_path = None
            st.session_state.current_history_name = ""
        return True
    except:
        return False

def rename_history(filepath, new_name):
    """Rename a saved history by updating its JSON name field."""
    try:
        with open(filepath, 'r', encoding='utf-8') as fp:
            data = json.load(fp)
        data["name"] = new_name
        with open(filepath, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)
        if st.session_state.get("current_history_path") == filepath:
            st.session_state.current_history_name = new_name
        return True
    except:
        return False

def get_sop_files():
    sops = []
    for pattern in ["*.md", "*.py"]:
        for f in sorted(glob.glob(os.path.join(MEMORY_DIR, pattern))):
            name = os.path.basename(f)
            try:
                with open(f, 'r', encoding='utf-8') as fp:
                    content = fp.read()
                sops.append({"path": f, "name": name, "content": content, "size": len(content)})
            except:
                sops.append({"path": f, "name": name, "content": "", "size": 0})
    return sops

def _init_agent():
    """Initialize GeneraticAgent + background thread, store in session."""
    agent = GeneraticAgent()
    threading.Thread(target=agent.run, daemon=True).start()
    st.session_state.agent = agent
    return agent

def new_chat():
    if st.session_state.get("agent"):
        st.session_state.agent.abort()
    _init_agent()
    st.session_state.messages = []
    st.session_state.current_history_path = None
    st.session_state.current_history_name = ""

# ─── Page Config ───
st.set_page_config(page_title="GenericAgent", page_icon="🤖", layout="wide")

# ─── Initialize Session State ───
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent" not in st.session_state:
    _init_agent()
if "current_history_path" not in st.session_state:
    st.session_state.current_history_path = None
if "current_history_name" not in st.session_state:
    st.session_state.current_history_name = ""

# ─── Sidebar ───
with st.sidebar:
    st.title("🤖 GenericAgent")
    
    if st.button("➕ 新建对话", use_container_width=True, type="primary"):
        new_chat()
        st.rerun()
    
    st.divider()
    
    # ── Settings ──
    with st.expander("⚙️ 设置", expanded=False):
        agent = st.session_state.get("agent")
        if agent and agent.llmclient:
            llms = agent.list_llms()
            current_idx = agent.llm_no
            llm_labels = [f"{'✅ ' if active else ''}{name}" for i, name, active in llms]
            selected = st.selectbox("LLM 后端", range(len(llms)), index=current_idx,
                                     format_func=lambda i: llm_labels[i])
            if selected != current_idx:
                agent.next_llm(selected)
                st.toast(f"已切换到 {llms[selected][1]}")
            
            verbose = st.toggle("详细输出", value=agent.verbose)
            agent.verbose = verbose
        
        if st.button("⏹️ 中断任务", use_container_width=True):
            if agent:
                agent.abort()
                st.toast("已发送中断信号")
    
    st.divider()
    
    # ══════════════════════════════════════
    # ── History Management ──
    # ══════════════════════════════════════
    st.subheader("💬 对话历史")
    
    col1, col2 = st.columns([3, 1])
    with col1:
        save_name = st.text_input("名称", value=st.session_state.get("current_history_name", ""),
                                   placeholder="自动命名", label_visibility="collapsed")
    with col2:
        if st.button("💾", help="保存当前对话", use_container_width=True):
            if st.session_state.messages:
                path = save_current_history(save_name)
                if path:
                    st.toast("✅ 对话已保存！")
                    st.rerun()
            else:
                st.toast("⚠️ 没有对话内容可保存")
    
    histories = get_saved_histories()
    if histories:
        for i, h in enumerate(histories[:20]):  # Show max 20
            editing_key = f"editing_hist_{i}"
            with st.container():
                if st.session_state.get(editing_key):
                    # ── 编辑模式 ──
                    new_name = st.text_input(
                        "重命名", value=h["name"],
                        key=f"rename_input_{i}", label_visibility="collapsed")
                    col_ok, col_cancel = st.columns(2)
                    with col_ok:
                        if st.button("✅", key=f"rename_ok_{i}", use_container_width=True):
                            if new_name.strip() and new_name.strip() != h["name"]:
                                rename_history(h["path"], new_name.strip())
                                st.toast(f"✅ 已重命名")
                            st.session_state[editing_key] = False
                            st.rerun()
                    with col_cancel:
                        if st.button("❌", key=f"rename_cancel_{i}", use_container_width=True):
                            st.session_state[editing_key] = False
                            st.rerun()
                else:
                    # ── 正常模式 ──
                    col_name, col_edit, col_del = st.columns([4, 1, 1])
                    with col_name:
                        is_current = st.session_state.get("current_history_path") == h["path"]
                        label = f"{'📌 ' if is_current else ''}{h['name']}"
                        if len(label) > 28:
                            label = label[:28] + "…"
                        ts = ""
                        if h["timestamp"]:
                            try:
                                dt = datetime.fromisoformat(h["timestamp"])
                                ts = dt.strftime("%m/%d %H:%M")
                            except: pass
                        
                        if st.button(f"{label}\n`{ts} · {h['msg_count']}条`",
                                    key=f"hist_{i}", use_container_width=True,
                                    disabled=is_current):
                            load_history(h["path"])
                            st.toast(f"✅ 已加载: {h['name']}")
                            st.rerun()
                    
                    with col_edit:
                        if st.button("✏️", key=f"edit_{i}", help="重命名"):
                            st.session_state[editing_key] = True
                            st.rerun()
                    
                    with col_del:
                        if st.button("🗑", key=f"del_{i}", help="删除"):
                            delete_history(h["path"])
                            st.toast("🗑️ 已删除")
                            st.rerun()
    else:
        st.caption("暂无保存的对话")
    
    st.divider()
    
    # ══════════════════════════════════════
    # ── SOP Management ──
    # ══════════════════════════════════════
    st.subheader("📋 SOP 管理")
    
    sops = get_sop_files()
    
    # Create new SOP
    with st.expander("➕ 新建 SOP", expanded=False):
        new_sop_name = st.text_input("文件名", placeholder="my_sop.md", key="new_sop_name")
        new_sop_content = st.text_area("内容", height=150, key="new_sop_content")
        if st.button("创建", key="create_sop", use_container_width=True):
            if new_sop_name and new_sop_content:
                if not new_sop_name.endswith(('.md', '.py', '.txt')):
                    new_sop_name += '.md'
                fpath = os.path.join(MEMORY_DIR, new_sop_name)
                with open(fpath, 'w', encoding='utf-8') as fp:
                    fp.write(new_sop_content)
                st.toast(f"✅ 已创建 {new_sop_name}")
                st.rerun()
            else:
                st.toast("⚠️ 请填写文件名和内容")
    
    # List existing SOPs
    if sops:
        for i, sop in enumerate(sops):
            with st.expander(f"📄 {sop['name']} ({sop['size']}B)", expanded=False):
                # Show content (truncated for display)
                display_content = sop['content'][:2000]
                if len(sop['content']) > 2000:
                    display_content += "\n... (truncated)"
                st.code(display_content, language="markdown" if sop['name'].endswith('.md') else "python")
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    if st.button("📎 调用", key=f"invoke_sop_{i}", use_container_width=True,
                                 help="将SOP内容注入对话"):
                        inject_msg = f"请参考以下SOP执行：\n\n---\n{sop['content']}\n---"
                        st.session_state.pending_sop = inject_msg
                        st.toast(f"📎 已准备注入 {sop['name']}")
                        st.rerun()
                with col_b:
                    if st.button("📝 编辑", key=f"edit_sop_{i}", use_container_width=True):
                        st.session_state[f"editing_sop_{i}"] = True
                        st.rerun()
                with col_c:
                    if st.button("🗑", key=f"del_sop_{i}", use_container_width=True, help="删除"):
                        os.remove(sop['path'])
                        st.toast(f"🗑️ 已删除 {sop['name']}")
                        st.rerun()
                
                # Edit mode
                if st.session_state.get(f"editing_sop_{i}"):
                    edited = st.text_area("编辑内容", value=sop['content'], height=300,
                                           key=f"sop_edit_area_{i}")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("保存", key=f"save_sop_{i}", use_container_width=True):
                            with open(sop['path'], 'w', encoding='utf-8') as fp:
                                fp.write(edited)
                            st.session_state[f"editing_sop_{i}"] = False
                            st.toast(f"✅ 已保存 {sop['name']}")
                            st.rerun()
                    with c2:
                        if st.button("取消", key=f"cancel_sop_{i}", use_container_width=True):
                            st.session_state[f"editing_sop_{i}"] = False
                            st.rerun()

# ─── Main Chat Area ───

# Show current status
agent = st.session_state.get("agent")
if agent and agent.llmclient:
    status = agent.get_llm_name()
    if agent.is_running:
        status += " 🔄 运行中"
    st.caption(f"🔗 {status}")

# Display chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Handle pending SOP injection
pending_sop = st.session_state.pop("pending_sop", None)

# Chat input
user_input = st.chat_input("输入消息...")

# Fix: IME回车 + macOS pywebview复制粘贴快捷键
import streamlit.components.v1 as components
components.html("""
<script>
(function() {
    if (window.parent.__imeFixInstalled2) return;
    window.parent.__imeFixInstalled2 = true;
    const doc = window.parent.document;
    let composing = false;
    doc.addEventListener('compositionstart', () => { composing = true; }, true);
    doc.addEventListener('compositionend', () => { composing = false; }, true);
    function installFix() {
        const textareas = doc.querySelectorAll('textarea[data-testid="stChatInputTextArea"]');
        textareas.forEach(ta => {
            if (ta.__imeFix2) return;
            ta.__imeFix2 = true;
            ta.addEventListener('keydown', function(e) {
                if (e.key === 'Enter' && !e.shiftKey &&
                    (e.isComposing || composing || e.keyCode === 229)) {
                    e.stopImmediatePropagation();
                    e.preventDefault();
                }
            }, true);
        });
    }
    installFix();
    const observer = new MutationObserver(() => installFix());
    observer.observe(doc.body, { childList: true, subtree: true });

    // Fix: macOS pywebview Cmd+C/V/X/A 快捷键支持
    if (!window.parent.__clipboardFixInstalled) {
        window.parent.__clipboardFixInstalled = true;
        doc.addEventListener('keydown', function(e) {
            if (!(e.metaKey || e.ctrlKey)) return;
            if (e.key === 'c') {
                const sel = doc.getSelection();
                if (sel && sel.toString()) {
                    e.preventDefault();
                    navigator.clipboard.writeText(sel.toString()).catch(() => {
                        doc.execCommand('copy');
                    });
                }
            } else if (e.key === 'x') {
                e.preventDefault();
                doc.execCommand('cut');
            } else if (e.key === 'v') {
                e.preventDefault();
                navigator.clipboard.readText().then(text => {
                    const active = doc.activeElement;
                    if (active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT')) {
                        const start = active.selectionStart;
                        const end = active.selectionEnd;
                        const val = active.value;
                        const nativeSet = Object.getOwnPropertyDescriptor(window.parent.HTMLTextAreaElement.prototype, 'value').set
                            || Object.getOwnPropertyDescriptor(window.parent.HTMLInputElement.prototype, 'value').set;
                        nativeSet.call(active, val.slice(0, start) + text + val.slice(end));
                        active.selectionStart = active.selectionEnd = start + text.length;
                        active.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }).catch(() => { doc.execCommand('paste'); });
            } else if (e.key === 'a') {
                const active = doc.activeElement;
                if (active && (active.tagName === 'TEXTAREA' || active.tagName === 'INPUT')) {
                    active.select();
                } else {
                    doc.execCommand('selectAll');
                }
                e.preventDefault();
            }
        }, true);
    }
})();
</script>
""", height=0)

if pending_sop and not user_input:
    user_input = pending_sop

if user_input:
    # Add user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)
    
    # Get agent response
    agent = st.session_state.get("agent")
    if agent and agent.llmclient:
        with st.chat_message("assistant"):
            with st.spinner("思考中..."):
                display_queue = agent.put_task(user_input)
                
                response_placeholder = st.empty()
                full_response = ""
                
                try:
                    while True:
                        try:
                            item = display_queue.get(timeout=300)  # 5 min timeout
                        except:
                            full_response += "\n\n⏱️ 响应超时"
                            break
                        
                        if 'done' in item:
                            full_response = item['done']
                            break
                        elif 'next' in item:
                            full_response = item['next']
                            response_placeholder.markdown(full_response + "▌")
                    
                    # Clean up display
                    if '</summary>' in full_response:
                        full_response = full_response.replace('</summary>', '</summary>\n\n')
                    if '</file_content>' in full_response:
                        full_response = re.sub(
                            r'<file_content>\s*(.*?)\s*</file_content>',
                            r'\n````\n<file_content>\n\1\n</file_content>\n````',
                            full_response, flags=re.DOTALL)
                    
                    response_placeholder.markdown(full_response)
                except Exception as e:
                    full_response = f"❌ 错误: {str(e)}"
                    response_placeholder.markdown(full_response)
        
        st.session_state.messages.append({"role": "assistant", "content": full_response})
    else:
        st.error("❌ Agent 未初始化或无可用的 LLM 后端")