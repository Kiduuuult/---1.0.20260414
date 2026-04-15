#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端冒烟测试（无真实 LLM / 无真实浏览器）：
1) 收集基础信息
2) 收图（含无后缀 CDN 链接）
3) 触发 discover
4) 补齐动态字段
5) 触发 fill 并完成
"""

import asyncio
import re
import time
import os
import sys
from fastapi.testclient import TestClient

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import app.main as main_mod


def _extractor_text(user_input: str):
    extracted = {}
    lower = user_input.lower()

    if "挖掘机" in user_input:
        extracted["machine_type"] = "挖掘机"
    if "二手" in user_input:
        extracted["is_new"] = "二手"

    year_match = re.search(r"(20\d{2})年", user_input)
    if year_match:
        extracted["manufacture_year"] = year_match.group(1)

    month_match = re.search(r"(\d{1,2})月", user_input)
    if month_match:
        extracted["manufacture_month"] = month_match.group(1)

    price_match = re.search(r"(\d+(?:\.\d+)?)\s*万", user_input)
    if price_match:
        extracted["price"] = price_match.group(1)

    if "联系人" in user_input:
        extracted["contact_name"] = "王先生"

    phone_match = re.search(r"(1\d{10})", user_input)
    if phone_match:
        extracted["contact_phone"] = phone_match.group(1)

    dyn_match = re.search(r"(?:小时数|小时)\s*(\d+)", lower)
    if dyn_match:
        extracted["dynamic_hours"] = dyn_match.group(1)

    return extracted


async def _fake_engine_chat(user_input, history, collected_info, dynamic_fields=None):
    merged = dict(collected_info)
    merged.update(_extractor_text(user_input))
    intent = bool(re.search(r"(开始发布|继续发布|确认发布)", user_input))
    return {
        "content": "已记录，继续补充信息。",
        "updated_collected_info": merged,
        "intent_to_publish": intent,
    }


async def _fake_rpa_run(car_info, mode="fill", qr_callback=None):
    await asyncio.sleep(0.05)
    if mode == "discover":
        return {
            "status": "success",
            "mode": "discover",
            "dynamic_fields": [
                {"id": "dynamic_hours", "name": "小时数", "description": "请输入小时数"}
            ],
        }
    return {"status": "success", "mode": "fill"}


def _wait_until(check_fn, timeout=3.0, interval=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if check_fn():
            return True
        time.sleep(interval)
    return False

def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def main():
    orig_engine_chat = main_mod.engine.chat
    orig_rpa_run = main_mod.car_post_skill.run

    main_mod.sessions.clear()
    main_mod.engine.chat = _fake_engine_chat
    main_mod.car_post_skill.run = _fake_rpa_run

    try:
        client = TestClient(main_mod.app)
        user_id = "smoke_user_e2e"

        # 1) 基础信息（先不带图片）
        r1 = client.post("/chat", json={
            "user_id": user_id,
            "message": "我要卖挖掘机，二手，2021年7月，15万，联系人王先生，电话13800138000"
        })
        assert r1.status_code == 200
        body1 = r1.json()
        assert body1["rpa_state"] in ("idle", "ready_to_fill")
        assert body1["collected_info"].get("image_urls") == []

        # 2) 收图（无后缀 URL，验证兼容识别）
        r2 = client.post("/chat", json={
            "user_id": user_id,
            "message": "图片给你：https://pic4.58cdn.com.cn/nowater/lbgfe/image/n_v3abc123?from=chat"
        })
        assert r2.status_code == 200
        body2 = r2.json()
        assert len(body2["collected_info"].get("image_urls", [])) == 1

        # 3) 触发 discover
        r3 = client.post("/chat", json={"user_id": user_id, "message": "开始发布"})
        assert r3.status_code == 200
        assert r3.json()["rpa_state"] in ("discovering", "waiting_login", "idle")

        # TestClient 下 create_task 触发的后台协程可能不会稳定执行，这里手动驱动一次。
        if main_mod.sessions[user_id].get("rpa_state") == "discovering":
            _run_async(main_mod.run_rpa_discovery_task(user_id))

        ok_discover = _wait_until(
            lambda: (
                client.get(f"/api/status?user_id={user_id}").json().get("dynamic_fields")
                and client.get(f"/api/status?user_id={user_id}").json().get("rpa_state") in ("need_dynamic_info", "idle")
            )
        )
        assert ok_discover, "discover 阶段未在预期时间内完成"

        # 4) 补齐动态字段
        r4 = client.post("/chat", json={"user_id": user_id, "message": "小时数 2500"})
        assert r4.status_code == 200
        body4 = r4.json()
        assert body4["collected_info"].get("dynamic_hours") == "2500"

        # 5) 触发 fill
        r5 = client.post("/chat", json={"user_id": user_id, "message": "继续发布"})
        assert r5.status_code == 200

        if main_mod.sessions[user_id].get("rpa_state") == "filling":
            _run_async(main_mod.run_rpa_fill_task(user_id))

        ok_done = _wait_until(
            lambda: client.get(f"/api/status?user_id={user_id}").json().get("rpa_state") == "done"
        )
        assert ok_done, "fill 阶段未在预期时间内完成"

        print("✅ e2e smoke passed")
    finally:
        main_mod.engine.chat = orig_engine_chat
        main_mod.car_post_skill.run = orig_rpa_run


if __name__ == "__main__":
    main()
