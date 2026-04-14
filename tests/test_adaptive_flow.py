# -*- coding: utf-8 -*-
import asyncio
import os
import sys
from dotenv import load_dotenv

# 将项目根目录加入路径
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.engine import NativeAgentEngine
from app.skills.car_post_rpa import car_post_skill

async def test_adaptive_flow():
    load_dotenv()
    
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL", "chatling-mini")
    
    engine = NativeAgentEngine(api_key=api_key, base_url=base_url, model=model)

    # 1. 初始状态
    session = {
        "history": [],
        "collected_info": {}
    }

    # 2. 用户输入核心信息
    user_msg = "我要卖台挖掘机，21年的，二手的，打算卖15万"
    print(f"\n👤 用户: {user_msg}")
    
    result = await engine.chat(user_msg, session["history"], session["collected_info"])
    session["collected_info"] = result["updated_collected_info"]
    print(f"🤖 Agent (第一阶段提取): {session['collected_info']}")

    # 3. 模拟触发 RPA 探测 (Discovery Mode)
    # 在真实流程中，当 Agent 发现机型已满，会自动触发 RPA
    print("\n🔍 [RPA] 正在根据机型探测网页动态字段...")
    # 这里我们直接手动触发 RPA 的探测模式
    # 为了演示，我们假设探测到了“品牌”和“小时数”
    # rpa_discovery = await car_post_skill.run(session["collected_info"], mode="discover")
    # mock 结果如下:
    discovery_result = [
        {"id": "dynamic_品牌", "name": "品牌", "description": "车辆的品牌"},
        {"id": "dynamic_小时数", "name": "小时数", "description": "设备已使用的小时数"}
    ]
    
    # 4. Agent 拿到探测结果，进行动态追问
    print(f"🤖 Agent 收到动态字段，准备追问...")
    follow_up_input = "好的，那这台挖机是什么品牌的？干了多少小时了？"
    
    # 我们模拟用户回答了这些动态字段
    user_reply_dynamic = "三一重工的，干了 2500 小时"
    print(f"\n👤 用户: {user_reply_dynamic}")
    
    result_final = await engine.chat(
        user_reply_dynamic, 
        session["history"], 
        session["collected_info"],
        dynamic_fields=discovery_result # 注入动态字段！
    )
    
    print(f"🤖 Agent (动态信息提取结果): {result_final['updated_collected_info']}")
    print(f"🤖 Agent 回复: {result_final['content']}")

if __name__ == "__main__":
    asyncio.run(test_adaptive_flow())
