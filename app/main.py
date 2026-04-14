# -*- coding: utf-8 -*-
import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from app.agent.engine import NativeAgentEngine
from app.skills.car_post_rpa import car_post_skill

load_dotenv()

app = FastAPI(title="ABG Native Agent - 专业级发帖助手")

os.makedirs("app/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

engine = NativeAgentEngine(
    api_key=os.getenv("LLM_API_KEY"),
    base_url=os.getenv("LLM_BASE_URL"),
    model=os.getenv("LLM_MODEL", "chatling-mini")
)

sessions = {}

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_id = data.get("user_id", "session_1")
    message = data.get("message", "")
    
    if user_id not in sessions:
        initial_info = {f.get("id"): "" for f in engine.fields if f.get("id") and not f.get("internal")}
        sessions[user_id] = {
            "history": [],
            "collected_info": initial_info,
            "dynamic_fields": [],
            "status": "等待收集信息",
            "rpa_state": "idle",              
            "rpa_task_running": False,
            "pending_rpa_result": None,
            "discovery_done": False
        }
    
    session = sessions[user_id]
    
    result = await engine.chat(
        user_input=message,
        history=session["history"],
        collected_info=session["collected_info"],
        dynamic_fields=session["dynamic_fields"]
    )
    
    session["history"].append({"role": "user", "content": message})
    session["history"].append({"role": "assistant", "content": result["content"]})
    session["collected_info"] = result["updated_collected_info"]

    _update_session_state(session)

    intent_to_publish = result.get("intent_to_publish", False)

    if session["rpa_state"] == "waiting_login" and intent_to_publish and not session["rpa_task_running"]:
        session["pending_rpa_result"] = None
        session["rpa_task_running"] = True
        if session["discovery_done"]:
             asyncio.create_task(run_rpa_fill_task(user_id))
        else:
             asyncio.create_task(run_rpa_discovery_task(user_id))
        result["content"] = f"【系统提示：恢复发布流程...】\n\n{result['content']}"

    elif intent_to_publish and not session["discovery_done"] and not session["rpa_task_running"]:
        session["status"] = "正在通过浏览器探测专属字段..."
        session["rpa_state"] = "discovering"
        session["rpa_task_running"] = True
        session["pending_rpa_result"] = None
        asyncio.create_task(run_rpa_discovery_task(user_id))
        result["content"] = f"【执行探测】好的，请看浏览器。我正在为您确认该机型所需的具体参数..."
    
    elif intent_to_publish and session["rpa_state"] == "ready_to_fill" and session["discovery_done"] and not session["rpa_task_running"]:
        session["status"] = "正在执行全量自动填表..."
        session["rpa_state"] = "filling"
        session["rpa_task_running"] = True
        session["pending_rpa_result"] = None
        asyncio.create_task(run_rpa_fill_task(user_id))
        result["content"] = f"【执行发布】信息已锁定，这就为您完成最终填表！"

    return JSONResponse(content={
        "message": result["content"],
        "collected_info": session["collected_info"],
        "rpa_status": session["status"],
        "rpa_result": session.get("pending_rpa_result"),
        "rpa_state": session["rpa_state"],
        "status": "success"
    })

def _update_session_state(session):
    if session["rpa_state"] in ("discovering", "filling", "waiting_login"):
        return

    missing = []
    for f in (engine.fields or []):
        if f.get("required") and not session["collected_info"].get(f.get("id")):
            missing.append(f.get("name"))
    
    for df in (session["dynamic_fields"] or []):
        if not session["collected_info"].get(df.get("id")):
            missing.append(df.get("name"))
    
    if not missing:
        if session["discovery_done"]:
            session["rpa_state"] = "ready_to_fill"
            session["status"] = "信息已收齐，随时可以执行发布"
        else:
            session["rpa_state"] = "idle"
            session["status"] = "基本信息已收集，引导探测中"
    else:
        if session["discovery_done"]:
            session["rpa_state"] = "need_dynamic_info"
            session["status"] = "探测完成，需补全额外参数"
        else:
            session["rpa_state"] = "idle"
            session["status"] = "正在收集基础信息..."

async def run_rpa_discovery_task(user_id: str):
    session = sessions[user_id]
    def on_qr(qr):
        session["pending_rpa_result"] = qr
        session["rpa_state"] = "waiting_login"
        session["status"] = "请扫码，浏览器将保持开启..."

    try:
        res = await car_post_skill.run(session["collected_info"], mode="discover", qr_callback=on_qr)
        if res.get("status") == "success":
            session["dynamic_fields"] = res.get("dynamic_fields", [])
            session["discovery_done"] = True
            session["rpa_state"] = "idle"  # 释放探测锁，允许状态机流转
            _update_session_state(session) 
        else:
            session["rpa_state"] = "error"
            session["status"] = f"探测失败: {res.get('message')}"
    except Exception as e:
        session["rpa_state"] = "error"
        session["status"] = f"探测报错: {str(e)}"
    finally:
        session["rpa_task_running"] = False

async def run_rpa_fill_task(user_id: str):
    session = sessions[user_id]
    def on_qr(qr):
        session["pending_rpa_result"] = qr
        session["rpa_state"] = "waiting_login"
        session["status"] = "请扫码，即将发布..."

    try:
        res = await car_post_skill.run(session["collected_info"], mode="fill", qr_callback=on_qr)
        if res.get("status") == "success":
            session["rpa_state"] = "done"
            session["status"] = "自动发布已圆满结束"
            # 只有在最终完成后，我们才考虑手动或自动关闭浏览器
            # await car_post_skill.close_browser()
        else:
            session["rpa_state"] = "error"
            session["status"] = f"填表异常: {res.get('message')}"
    except Exception as e:
        session["rpa_state"] = "error"
        session["status"] = f"填表报错: {str(e)}"
    finally:
        session["rpa_task_running"] = False

@app.get("/")
async def read_index(): return FileResponse("app/static/index.html")

@app.get("/api/status")
async def get_status(user_id: str):
    s = sessions.get(user_id)
    if not s: return JSONResponse(status_code=404, content={"message": "No session"})
    
    bot_hint = ""
    if s["rpa_state"] in ("need_dynamic_info", "idle") and s["discovery_done"]:
        missing = []
        # 基础必填项 (如：出厂年份、月份)
        for f in (engine.fields or []):
            if f.get("required") and not s["collected_info"].get(f.get("id")):
                missing.append(f"【{f.get('name')}】")
        
        # 动态必填项
        for df in s["dynamic_fields"]:
             if not s["collected_info"].get(df["id"]):
                 if "吨" in df["name"]: missing.append(f"【{df['name']}（吨）】")
                 elif "程" in df["name"]: missing.append(f"【{df['name']}（千米）】")
                 elif "小时" in df["name"]: missing.append(f"【{df['name']}（小时）】")
                 else: missing.append(f"【{df['name']}】")
        
        if missing:
            bot_hint = f"探测成功！由于您选择了{s['collected_info'].get('machine_type')}，浏览器已为您停留在动态表单页。还需麻烦告知：{'、'.join(missing)}。请直接告诉我数值即可。"

    return {
        "collected_info": s["collected_info"],
        "dynamic_fields": s["dynamic_fields"], 
        "base_fields": engine.fields,  # 新增：传递基础字段元数据
        "rpa_status": s["status"],
        "rpa_result": s.get("pending_rpa_result"),
        "rpa_state": s.get("rpa_state"),
        "bot_hint": bot_hint
    }
